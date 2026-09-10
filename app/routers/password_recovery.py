"""Secure Super Admin password recovery with five configured security questions."""
from __future__ import annotations

import random
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main as main_module
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, User
from app.security import hash_password, verify_password
from app.security_question_models import SuperAdminSecurityQuestion

app = main_module.app
router = APIRouter(tags=["password-recovery"])

RECOVERY_SESSION_USER = "super_admin_recovery_user_id"
RECOVERY_SESSION_EXPIRES = "super_admin_recovery_expires"
RECOVERY_SESSION_QUESTIONS = "super_admin_recovery_questions"
RECOVERY_TTL_SECONDS = 10 * 60
_MAX_FAILURES = 5
_WINDOW_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}

SECURITY_QUESTIONS = (
    "What was the name of your first school?",
    "What is the name of the city where you were born?",
    "What was your childhood nickname?",
    "What is the name of your favourite teacher?",
    "What was the first vehicle you owned?",
)


def _rate_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


def _rate_limited(request: Request, username: str) -> bool:
    now = time.time()
    key = _rate_key(request, username)
    attempts = [t for t in _failures.get(key, []) if now - t < _WINDOW_SECONDS]
    _failures[key] = attempts
    return len(attempts) >= _MAX_FAILURES


def _record_failure(request: Request, username: str) -> None:
    now = time.time()
    key = _rate_key(request, username)
    attempts = [t for t in _failures.get(key, []) if now - t < _WINDOW_SECONDS]
    attempts.append(now)
    _failures[key] = attempts


def _clear_recovery(request: Request) -> None:
    for key in (RECOVERY_SESSION_USER, RECOVERY_SESSION_EXPIRES, RECOVERY_SESSION_QUESTIONS, "super_admin_recovery_verified"):
        request.session.pop(key, None)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>MetroCRM | {title}</title>"
        "<style>body{margin:0;background:#f4f7fb;color:#10213f;font-family:Inter,Arial,sans-serif;display:grid;place-items:center;min-height:100vh;padding:24px}.card{width:min(560px,100%);background:#fff;border:1px solid #dbe4ef;border-radius:20px;padding:30px;box-shadow:0 20px 60px #10213f18}h1{margin:0 0 10px;font-size:28px}p{color:#64748b;line-height:1.55}.field{margin:18px 0}.field label{display:block;font-weight:700;font-size:13px;margin-bottom:7px}.field input,.field select{width:100%;height:48px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:0 13px;font-size:14px}.button{width:100%;height:50px;border:0;border-radius:10px;background:#1677ff;color:#fff;font-weight:800;cursor:pointer}.alert{background:#fff1f2;color:#9f1239;border:1px solid #fecdd3;padding:11px 13px;border-radius:10px;margin:15px 0}.ok{background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0;padding:11px 13px;border-radius:10px;margin:15px 0}.back{display:inline-block;margin-top:18px;color:#1677ff;text-decoration:none;font-weight:700;font-size:13px}.question{padding:14px 16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;margin:14px 0}</style></head><body>"
        f"<main class='card'>{body}</main></body></html>"
    )


def _super_admin_from_session(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id or request.session.get("login_portal") != "super_admin":
        return None
    user = db.get(User, user_id)
    if not user or user.role != "SUPER_ADMIN" or not user.is_active:
        return None
    return user


@app.get("/super-admin/security-questions", response_class=HTMLResponse)
def security_questions_page(request: Request, db: Session = Depends(get_db)):
    user = _super_admin_from_session(request, db)
    if not user:
        return RedirectResponse("/super-admin/login", status_code=303)
    rows = {row.question_no: row for row in db.scalars(select(SuperAdminSecurityQuestion).where(SuperAdminSecurityQuestion.user_id == user.id, SuperAdminSecurityQuestion.is_active.is_(True))).all()}
    fields = []
    for number, question in enumerate(SECURITY_QUESTIONS, 1):
        fields.append(f"<div class='question'><strong>{number}. {question}</strong><div class='field'><label for='answer_{number}'>Answer</label><input id='answer_{number}' name='answer_{number}' type='password' autocomplete='off' placeholder='Enter your private answer'></div></div>")
    status = "<div class='ok'>All five recovery questions are configured.</div>" if len(rows) == 5 else "<div class='alert'>Configure all five questions before relying on password recovery. During recovery, any two questions will be selected at random.</div>"
    body = "<h1>Super Admin Recovery Questions</h1><p>Set five private answers. MetroCRM stores only password hashes for the answers. During password recovery, two of these five questions are selected at random.</p>" + status + "<form method='post' action='/super-admin/security-questions'>" + "".join(fields) + f"<input type='hidden' name='csrf_token' value='{csrf_token(request)}'><button class='button' type='submit'>Save Recovery Questions</button></form><a class='back' href='/dashboard'>← Back to Dashboard</a>"
    return _page("Recovery Questions", body)


@app.post("/super-admin/security-questions", dependencies=[Depends(require_csrf)])
def save_security_questions(request: Request, answer_1: str = Form(""), answer_2: str = Form(""), answer_3: str = Form(""), answer_4: str = Form(""), answer_5: str = Form(""), db: Session = Depends(get_db)):
    user = _super_admin_from_session(request, db)
    if not user:
        return RedirectResponse("/super-admin/login", status_code=303)
    answers = [answer_1.strip(), answer_2.strip(), answer_3.strip(), answer_4.strip(), answer_5.strip()]
    if any(len(answer) < 2 for answer in answers):
        return _page("Recovery Questions", "<div class='alert'>Please provide a meaningful answer for all five questions. All five are required.</div><a class='back' href='/super-admin/security-questions'>Try again</a>")
    db.query(SuperAdminSecurityQuestion).filter(SuperAdminSecurityQuestion.user_id == user.id).delete(synchronize_session=False)
    for number, (question, answer) in enumerate(zip(SECURITY_QUESTIONS, answers), 1):
        db.add(SuperAdminSecurityQuestion(user_id=user.id, question_no=number, question=question, answer_hash=hash_password(answer), is_active=True))
    db.add(AuditEvent(actor_user_id=user.id, action="SUPER_ADMIN_RECOVERY_QUESTIONS_UPDATED", entity_type="User", entity_id=str(user.id), details='{"question_count":5}'))
    db.commit()
    return RedirectResponse("/super-admin/security-questions?saved=1", status_code=303)


@app.get("/super-admin/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, db: Session = Depends(get_db)):
    token = csrf_token(request)
    body = (
        "<h1>Reset Super Admin Password</h1>"
        "<p>Enter your Super Admin username. MetroCRM will then ask two security questions selected at random from your five configured recovery questions.</p>"
        "<form method='post' action='/super-admin/forgot-password'>"
        "<div class='field'><label for='username'>Username</label><input id='username' name='username' required autocomplete='username'></div>"
        f"<input type='hidden' name='csrf_token' value='{token}'>"
        "<button class='button' type='submit'>Continue to Security Verification</button></form>"
        "<a class='back' href='/super-admin/login'>← Back to Super Admin Login</a>"
    )
    return _page("Password Recovery", body)


@app.post("/super-admin/forgot-password", dependencies=[Depends(require_csrf)])
def start_recovery(request: Request, username: str = Form(...), db: Session = Depends(get_db)):
    username = username.strip()
    if _rate_limited(request, username):
        return _page("Password Recovery", "<h1>Recovery temporarily locked</h1><p>Too many unsuccessful recovery attempts. Please try again later.</p><a class='back' href='/super-admin/login'>← Back to Super Admin Login</a>")
    user = db.scalar(select(User).where(User.username == username, User.role == "SUPER_ADMIN", User.is_active.is_(True)))
    if not user:
        _record_failure(request, username)
        return _page("Password Recovery", "<div class='alert'>The recovery request could not be verified.</div><a class='back' href='/super-admin/forgot-password'>Try again</a>")
    questions = db.scalars(select(SuperAdminSecurityQuestion).where(SuperAdminSecurityQuestion.user_id == user.id, SuperAdminSecurityQuestion.is_active.is_(True)).order_by(SuperAdminSecurityQuestion.question_no.asc())).all()
    if len(questions) != 5:
        return _page("Password Recovery", "<div class='alert'>Password recovery is not fully configured for this Super Admin account. Please contact another authorized Super Admin to configure all five recovery questions.</div><a class='back' href='/super-admin/login'>← Back to Super Admin Login</a>")
    selected = random.sample(questions, 2)
    request.session.clear()
    request.session[RECOVERY_SESSION_USER] = user.id
    request.session[RECOVERY_SESSION_EXPIRES] = time.time() + RECOVERY_TTL_SECONDS
    request.session[RECOVERY_SESSION_QUESTIONS] = [row.id for row in selected]
    token = csrf_token(request)
    body = "<h1>Security Verification</h1><p>Answer both questions correctly. These questions were selected at random.</p><form method='post' action='/super-admin/forgot-password/verify'>"
    for index, row in enumerate(selected, 1):
        body += f"<div class='question'><strong>{index}. {row.question}</strong><div class='field'><label for='answer_{index}'>Your Answer</label><input id='answer_{index}' name='answer_{index}' type='password' required autocomplete='off'></div></div>"
    body += f"<input type='hidden' name='csrf_token' value='{token}'><button class='button' type='submit'>Verify Answers</button></form>"
    return _page("Security Verification", body)


@app.post("/super-admin/forgot-password/verify", dependencies=[Depends(require_csrf)])
def verify_recovery(request: Request, answer_1: str = Form(...), answer_2: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get(RECOVERY_SESSION_USER)
    expires = request.session.get(RECOVERY_SESSION_EXPIRES, 0)
    question_ids = request.session.get(RECOVERY_SESSION_QUESTIONS, [])
    user = db.get(User, user_id) if user_id else None
    if not user or user.role != "SUPER_ADMIN" or not user.is_active or float(expires or 0) <= time.time() or not isinstance(question_ids, list) or len(question_ids) != 2:
        _clear_recovery(request)
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    rows = db.scalars(select(SuperAdminSecurityQuestion).where(SuperAdminSecurityQuestion.id.in_(question_ids), SuperAdminSecurityQuestion.user_id == user.id, SuperAdminSecurityQuestion.is_active.is_(True))).all()
    by_id = {row.id: row for row in rows}
    try:
        ordered = [by_id.get(int(question_ids[0])), by_id.get(int(question_ids[1]))]
    except (TypeError, ValueError):
        ordered = [None, None]
    valid = all(row is not None for row in ordered) and verify_password(answer_1.strip(), ordered[0].answer_hash) and verify_password(answer_2.strip(), ordered[1].answer_hash)
    if not valid:
        _record_failure(request, user.username)
        _clear_recovery(request)
        return _page("Password Recovery", "<div class='alert'>One or more answers were incorrect. For security, the recovery session has been closed. Start the recovery process again.</div><a class='back' href='/super-admin/forgot-password'>Try again</a>")
    request.session[RECOVERY_SESSION_EXPIRES] = time.time() + RECOVERY_TTL_SECONDS
    request.session["super_admin_recovery_verified"] = True
    return RedirectResponse("/super-admin/forgot-password/reset", status_code=303)


@app.get("/super-admin/forgot-password/reset", response_class=HTMLResponse)
def reset_password_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get(RECOVERY_SESSION_USER)
    expires = request.session.get(RECOVERY_SESSION_EXPIRES, 0)
    if not request.session.get("super_admin_recovery_verified"):
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    user = db.get(User, user_id) if user_id else None
    if not user or user.role != "SUPER_ADMIN" or not user.is_active or float(expires or 0) <= time.time():
        _clear_recovery(request)
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    body = (
        "<h1>Create a New Password</h1>"
        "<p>Security verification passed. Set a strong password of at least 8 characters.</p>"
        "<form method='post' action='/super-admin/forgot-password/reset'>"
        "<div class='field'><label for='new_password'>New Password</label><input id='new_password' name='new_password' type='password' required minlength='8' autocomplete='new-password'></div>"
        "<div class='field'><label for='confirm_password'>Re-enter New Password</label><input id='confirm_password' name='confirm_password' type='password' required minlength='8' autocomplete='new-password'></div>"
        f"<input type='hidden' name='csrf_token' value='{csrf_token(request)}'>"
        "<button class='button' type='submit'>Update Password Securely</button></form>"
    )
    return _page("Create New Password", body)


@app.post("/super-admin/forgot-password/reset", dependencies=[Depends(require_csrf)])
def reset_password(request: Request, new_password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get(RECOVERY_SESSION_USER)
    expires = request.session.get(RECOVERY_SESSION_EXPIRES, 0)
    if not request.session.get("super_admin_recovery_verified"):
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    user = db.get(User, user_id) if user_id else None
    if not user or user.role != "SUPER_ADMIN" or not user.is_active or float(expires or 0) <= time.time():
        _clear_recovery(request)
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    if len(new_password) < 8 or new_password != confirm_password:
        return _page("Create New Password", "<div class='alert'>The new passwords must match and contain at least 8 characters.</div><a class='back' href='/super-admin/forgot-password/reset'>Try again</a>")
    user.password_hash = hash_password(new_password)
    user.session_version += 1
    db.add(AuditEvent(actor_user_id=user.id, action="SUPER_ADMIN_PASSWORD_RECOVERED", entity_type="User", entity_id=str(user.id), details='{"method":"two_random_security_questions"}'))
    db.commit()
    _clear_recovery(request)
    request.session.clear()
    return RedirectResponse("/super-admin/login?password_reset=success", status_code=303)
