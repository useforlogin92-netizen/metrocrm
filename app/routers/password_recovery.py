"""Secure Super Admin password recovery flow."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main as main_module
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, User
from app.security import hash_password, verify_password

router = APIRouter(tags=["password-recovery"])

RECOVERY_SESSION_USER = "super_admin_recovery_user_id"
RECOVERY_SESSION_EXPIRES = "super_admin_recovery_expires"
RECOVERY_TTL_SECONDS = 10 * 60
_MAX_FAILURES = 5
_WINDOW_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}


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
    request.session.pop(RECOVERY_SESSION_USER, None)
    request.session.pop(RECOVERY_SESSION_EXPIRES, None)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>MetroCRM | {title}</title>"
        "<style>body{margin:0;background:#f4f7fb;color:#10213f;font-family:Inter,Arial,sans-serif;display:grid;place-items:center;min-height:100vh;padding:24px}.card{width:min(480px,100%);background:#fff;border:1px solid #dbe4ef;border-radius:20px;padding:30px;box-shadow:0 20px 60px #10213f18}h1{margin:0 0 10px;font-size:28px}p{color:#64748b;line-height:1.55}.field{margin:18px 0}.field label{display:block;font-weight:700;font-size:13px;margin-bottom:7px}.field input{width:100%;height:48px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:0 13px;font-size:14px}.button{width:100%;height:50px;border:0;border-radius:10px;background:#1677ff;color:#fff;font-weight:800;cursor:pointer}.alert{background:#fff1f2;color:#9f1239;border:1px solid #fecdd3;padding:11px 13px;border-radius:10px;margin:15px 0}.back{display:inline-block;margin-top:18px;color:#1677ff;text-decoration:none;font-weight:700;font-size:13px}</style></head><body>"
        f"<main class='card'>{body}</main></body></html>"
    )


@router.get("/super-admin/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    token = csrf_token(request)
    body = (
        "<h1>Reset Super Admin Password</h1>"
        "<p>Use the registered Super Admin username and security answer to verify ownership and create a new password.</p>"
        "<form method='post' action='/super-admin/forgot-password'>"
        "<div class='field'><label for='username'>Username</label><input id='username' name='username' required autocomplete='username'></div>"
        "<div class='field'><label for='security_answer'>Security Answer</label><input id='security_answer' name='security_answer' type='password' required autocomplete='off'></div>"
        f"<input type='hidden' name='csrf_token' value='{token}'>"
        "<button class='button' type='submit'>Verify and Continue</button></form>"
        "<a class='back' href='/super-admin/login'>← Back to Super Admin Login</a>"
    )
    return _page("Password Recovery", body)


@router.post("/super-admin/forgot-password", dependencies=[Depends(require_csrf)])
def verify_recovery(request: Request, username: str = Form(...), security_answer: str = Form(...), db: Session = Depends(get_db)):
    username = username.strip()
    if _rate_limited(request, username):
        return _page("Password Recovery", "<h1>Recovery temporarily locked</h1><p>Too many unsuccessful recovery attempts. Please try again later or use another authorized Super Admin account to assist with recovery.</p><a class='back' href='/super-admin/login'>← Back to Super Admin Login</a>")

    user = db.scalar(select(User).where(User.username == username, User.role == "SUPER_ADMIN"))
    valid = bool(user and user.is_active and user.security_answer_hash and verify_password(security_answer.strip(), user.security_answer_hash))
    if not valid:
        _record_failure(request, username)
        return _page("Password Recovery", "<div class='alert'>The recovery details could not be verified. Please check the username and security answer.</div><a class='back' href='/super-admin/forgot-password'>Try again</a>")

    _clear_recovery(request)
    request.session[RECOVERY_SESSION_USER] = user.id
    request.session[RECOVERY_SESSION_EXPIRES] = time.time() + RECOVERY_TTL_SECONDS
    request.session["password_recovery_csrf"] = csrf_token(request)
    return RedirectResponse("/super-admin/forgot-password/reset", status_code=303)


@router.get("/super-admin/forgot-password/reset", response_class=HTMLResponse)
def reset_password_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get(RECOVERY_SESSION_USER)
    expires = request.session.get(RECOVERY_SESSION_EXPIRES, 0)
    user = db.get(User, user_id) if user_id else None
    if not user or user.role != "SUPER_ADMIN" or not user.is_active or float(expires or 0) <= time.time():
        _clear_recovery(request)
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    token = request.session.get("password_recovery_csrf") or csrf_token(request)
    body = (
        "<h1>Create a New Password</h1>"
        "<p>Set a strong password of at least 8 characters. Your existing sessions will be invalidated after the password is changed.</p>"
        "<form method='post' action='/super-admin/forgot-password/reset'>"
        "<div class='field'><label for='new_password'>New Password</label><input id='new_password' name='new_password' type='password' required minlength='8' autocomplete='new-password'></div>"
        "<div class='field'><label for='confirm_password'>Confirm New Password</label><input id='confirm_password' name='confirm_password' type='password' required minlength='8' autocomplete='new-password'></div>"
        f"<input type='hidden' name='csrf_token' value='{token}'>"
        "<button class='button' type='submit'>Update Password</button></form>"
    )
    return _page("Create New Password", body)


@router.post("/super-admin/forgot-password/reset", dependencies=[Depends(require_csrf)])
def reset_password(request: Request, new_password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get(RECOVERY_SESSION_USER)
    expires = request.session.get(RECOVERY_SESSION_EXPIRES, 0)
    user = db.get(User, user_id) if user_id else None
    if not user or user.role != "SUPER_ADMIN" or not user.is_active or float(expires or 0) <= time.time():
        _clear_recovery(request)
        return RedirectResponse("/super-admin/forgot-password", status_code=303)
    if len(new_password) < 8 or new_password != confirm_password:
        return _page("Create New Password", "<div class='alert'>The new passwords must match and contain at least 8 characters.</div><a class='back' href='/super-admin/forgot-password/reset'>Try again</a>")

    user.password_hash = hash_password(new_password)
    user.session_version += 1
    db.add(AuditEvent(actor_user_id=user.id, action="SUPER_ADMIN_PASSWORD_RECOVERED", entity_type="User", entity_id=str(user.id), details='{"method":"security_question"}'))
    db.commit()
    _clear_recovery(request)
    request.session.clear()
    return RedirectResponse("/super-admin/login?password_reset=success", status_code=303)
