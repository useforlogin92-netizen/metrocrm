"""Role-aware forgot-password recovery for Admin and staff accounts."""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, DataRequest, User
from app.security import hash_password, verify_password

router = APIRouter(tags=["password-recovery"])

REQUEST_TTL_SECONDS = 15 * 60
MAX_PASSWORD_RESET_REQUESTS = 3
REQUEST_WINDOW_SECONDS = 15 * 60
_failure_log: dict[str, list[float]] = {}

STAFF_ROLES = {"MANAGER", "TL", "TELECALLER", "USER"}
APPROVER_ROLES = {"ADMIN", "SUPER_ADMIN"}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>MetroCRM | {title}</title>"
        "<style>body{margin:0;background:#f4f7fb;color:#10213f;font-family:Inter,Arial,sans-serif;display:grid;place-items:center;min-height:100vh;padding:24px}.card{width:min(650px,100%);background:#fff;border:1px solid #dbe4ef;border-radius:20px;padding:30px;box-shadow:0 20px 60px #10213f18}h1{margin:0 0 10px;font-size:28px}h2{font-size:18px;margin:24px 0 8px}p{color:#64748b;line-height:1.55}.field{margin:18px 0}.field label{display:block;font-weight:700;font-size:13px;margin-bottom:7px}.field input,.field select{width:100%;height:48px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:0 13px;font-size:14px}.button{width:100%;height:50px;border:0;border-radius:10px;background:#1677ff;color:#fff;font-weight:800;cursor:pointer}.secondary{background:#475569}.danger{background:#b91c1c}.alert{background:#fff1f2;color:#9f1239;border:1px solid #fecdd3;padding:11px 13px;border-radius:10px;margin:15px 0}.ok{background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0;padding:11px 13px;border-radius:10px;margin:15px 0}.request{padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;margin:14px 0}.actions{display:flex;gap:10px;margin-top:12px}.actions form{flex:1}.back{display:inline-block;margin-top:18px;color:#1677ff;text-decoration:none;font-weight:700;font-size:13px}</style></head><body>"
        f"<main class='card'>{body}</main></body></html>"
    )


def _rate_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


def _rate_limited(request: Request, username: str) -> bool:
    now = time.time()
    key = _rate_key(request, username)
    attempts = [t for t in _failure_log.get(key, []) if now - t < REQUEST_WINDOW_SECONDS]
    _failure_log[key] = attempts
    return len(attempts) >= MAX_PASSWORD_RESET_REQUESTS


def _record_failure(request: Request, username: str) -> None:
    now = time.time()
    key = _rate_key(request, username)
    attempts = [t for t in _failure_log.get(key, []) if now - t < REQUEST_WINDOW_SECONDS]
    attempts.append(now)
    _failure_log[key] = attempts


def _config(request: Request, user: User, method: str, raw_token: str) -> dict:
    return {
        "method": method,
        "token_hash": hashlib.sha256(raw_token.encode()).hexdigest(),
        "expires_at": time.time() + REQUEST_TTL_SECONDS,
        "allowed_approvers": ["SUPER_ADMIN"] if user.role == "ADMIN" else ["ADMIN", "SUPER_ADMIN"],
    }


def _parse_config(request_row: DataRequest) -> dict:
    try:
        value = json.loads(request_row.filters_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _current_approver(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active or user.role not in APPROVER_ROLES:
        return None
    return user


def _current_reset_request(request: Request, db: Session) -> tuple[DataRequest | None, User | None, str | None]:
    request_id = request.session.get("password_reset_request_id")
    raw_token = request.session.get("password_reset_token")
    if not request_id or not raw_token:
        return None, None, None
    row = db.get(DataRequest, request_id)
    if not row or row.action != "PASSWORD_RESET":
        return None, None, None
    user = db.get(User, row.requester_id)
    config = _parse_config(row)
    if not user or not config or float(config.get("expires_at", 0)) <= time.time():
        return None, None, None
    expected = str(config.get("token_hash", ""))
    actual = hashlib.sha256(str(raw_token).encode()).hexdigest()
    if not secrets.compare_digest(expected, actual):
        return None, None, None
    return row, user, str(raw_token)


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    token = csrf_token(request)
    body = (
        "<h1>Forgot Password</h1>"
        "<p>Choose the recovery method available for your account. Admin accounts can use Super Admin approval or their configured security question. Manager, TL, Telecaller and User accounts use Admin/Super Admin approval.</p>"
        "<form method='post' action='/forgot-password'>"
        "<div class='field'><label for='username'>Username</label><input id='username' name='username' required autocomplete='username'></div>"
        "<div class='field'><label for='method'>Recovery Method</label><select id='method' name='method' required><option value='approval'>Admin / Super Admin Approval</option><option value='security_question'>My Security Question (Admin only)</option></select></div>"
        f"<input type='hidden' name='csrf_token' value='{token}'>"
        "<button class='button' type='submit'>Continue</button></form>"
        "<a class='back' href='/'>← Back to Login</a>"
    )
    return _page("Forgot Password", body)


@router.post("/forgot-password", dependencies=[Depends(require_csrf)])
def start_recovery(request: Request, username: str = Form(...), method: str = Form("approval"), db: Session = Depends(get_db)):
    username = username.strip()
    if not username or _rate_limited(request, username):
        return _page("Forgot Password", "<div class='alert'>This recovery request cannot be processed right now. Please try again later.</div><a class='back' href='/forgot-password'>Try again</a>")

    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if not user or user.role == "SUPER_ADMIN" or user.role not in (STAFF_ROLES | {"ADMIN"}):
        _record_failure(request, username)
        return _page("Forgot Password", "<div class='alert'>This recovery request could not be verified.</div><a class='back' href='/forgot-password'>Try again</a>")

    if method == "security_question":
        if user.role != "ADMIN" or not user.security_question or not user.security_answer_hash:
            return _page("Forgot Password", "<div class='alert'>A personal security question is not configured for this Admin account. Use Super Admin approval instead.</div><a class='back' href='/forgot-password'>Try again</a>")
        request.session.clear()
        request.session["password_recovery_user_id"] = user.id
        request.session["password_recovery_security_question"] = user.security_question
        token = csrf_token(request)
        body = (
            "<h1>Admin Security Verification</h1>"
            "<p>Answer your configured private security question. The answer is stored only as a one-way password hash.</p>"
            f"<div class='request'><strong>{user.security_question}</strong></div>"
            "<form method='post' action='/forgot-password/security-question'>"
            "<div class='field'><label for='answer'>Your Answer</label><input id='answer' name='answer' type='password' required autocomplete='off'></div>"
            f"<input type='hidden' name='csrf_token' value='{token}'>"
            "<button class='button' type='submit'>Verify and Continue</button></form>"
            "<a class='back' href='/forgot-password'>← Choose another method</a>"
        )
        return _page("Admin Security Verification", body)

    if method != "approval":
        return _page("Forgot Password", "<div class='alert'>Invalid recovery method.</div><a class='back' href='/forgot-password'>Try again</a>")

    raw_token = secrets.token_urlsafe(32)
    row = DataRequest(
        requester_id=user.id,
        action="PASSWORD_RESET",
        entity_type="User",
        filters_json=json.dumps(_config(request, user, "approval", raw_token)),
        reason="Forgot password recovery request",
        status="PENDING",
    )
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor_user_id=user.id, action="PASSWORD_RESET_REQUESTED", entity_type="User", entity_id=str(user.id), details=json.dumps({"method": "approval"})))
    db.commit()
    request.session.clear()
    request.session["password_reset_request_id"] = row.id
    request.session["password_reset_token"] = raw_token
    return RedirectResponse("/forgot-password/status", status_code=303)


@router.post("/forgot-password/security-question", dependencies=[Depends(require_csrf)])
def verify_admin_security_question(request: Request, answer: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get("password_recovery_user_id")
    user = db.get(User, user_id) if user_id else None
    if not user or user.role != "ADMIN" or not user.is_active or not user.security_answer_hash:
        request.session.clear()
        return RedirectResponse("/forgot-password", status_code=303)
    if not verify_password(answer.strip(), user.security_answer_hash):
        _record_failure(request, user.username)
        request.session.clear()
        return _page("Forgot Password", "<div class='alert'>The answer was incorrect. The recovery session has been closed.</div><a class='back' href='/forgot-password'>Try again</a>")
    raw_token = secrets.token_urlsafe(32)
    row = DataRequest(
        requester_id=user.id,
        action="PASSWORD_RESET",
        entity_type="User",
        filters_json=json.dumps(_config(request, user, "security_question", raw_token)),
        reason="Admin forgot password verified by security question",
        status="APPROVED",
        decided_by_id=user.id,
    )
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor_user_id=user.id, action="PASSWORD_RESET_SECURITY_QUESTION_VERIFIED", entity_type="User", entity_id=str(user.id), details=json.dumps({"method": "security_question"})))
    db.commit()
    request.session.clear()
    request.session["password_reset_request_id"] = row.id
    request.session["password_reset_token"] = raw_token
    return RedirectResponse("/forgot-password/reset", status_code=303)


@router.get("/forgot-password/status", response_class=HTMLResponse)
def recovery_status(request: Request, db: Session = Depends(get_db)):
    row, user, _ = _current_reset_request(request, db)
    if not row or not user:
        request.session.clear()
        return RedirectResponse("/forgot-password", status_code=303)
    if row.status == "APPROVED":
        return RedirectResponse("/forgot-password/reset", status_code=303)
    if row.status == "REJECTED":
        request.session.clear()
        return _page("Forgot Password", "<div class='alert'>The recovery request was not approved. Please submit a new request.</div><a class='back' href='/forgot-password'>Start again</a>")
    body = (
        "<h1>Approval Pending</h1>"
        f"<p>Your password recovery request for <strong>{user.username}</strong> has been sent to the authorized administrator(s). Admin and Super Admin approval rules depend on your role.</p>"
        "<div class='ok'>Keep this page open. Refresh after the authorized administrator approves the request.</div>"
        "<form method='get' action='/forgot-password/status'><button class='button' type='submit'>Check Approval Status</button></form>"
    )
    return _page("Approval Pending", body)


@router.get("/forgot-password/reset", response_class=HTMLResponse)
def reset_page(request: Request, db: Session = Depends(get_db)):
    row, user, _ = _current_reset_request(request, db)
    if not row or not user or row.status != "APPROVED":
        return RedirectResponse("/forgot-password/status", status_code=303)
    token = csrf_token(request)
    body = (
        "<h1>Create a New Password</h1>"
        "<p>Identity verification is complete. Create a new password and enter it again to confirm.</p>"
        "<form method='post' action='/forgot-password/reset'>"
        "<div class='field'><label for='new_password'>New Password</label><input id='new_password' name='new_password' type='password' minlength='8' required autocomplete='new-password'></div>"
        "<div class='field'><label for='confirm_password'>Re-enter New Password</label><input id='confirm_password' name='confirm_password' type='password' minlength='8' required autocomplete='new-password'></div>"
        f"<input type='hidden' name='csrf_token' value='{token}'>"
        "<button class='button' type='submit'>Update Password Securely</button></form>"
    )
    return _page("Create New Password", body)


@router.post("/forgot-password/reset", dependencies=[Depends(require_csrf)])
def reset_password(request: Request, new_password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    row, user, _ = _current_reset_request(request, db)
    if not row or not user or row.status != "APPROVED":
        request.session.clear()
        return RedirectResponse("/forgot-password", status_code=303)
    if len(new_password) < 8 or new_password != confirm_password:
        return _page("Create New Password", "<div class='alert'>The new passwords must match and contain at least 8 characters.</div><a class='back' href='/forgot-password/reset'>Try again</a>")
    user.password_hash = hash_password(new_password)
    user.session_version += 1
    row.status = "COMPLETED"
    config = _parse_config(row)
    config["used_at"] = time.time()
    row.filters_json = json.dumps(config)
    db.add(AuditEvent(actor_user_id=user.id, action="PASSWORD_RESET_COMPLETED", entity_type="User", entity_id=str(user.id), details=json.dumps({"method": config.get("method")})))
    db.commit()
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/password-reset-requests", response_class=HTMLResponse)
def password_reset_requests(request: Request, db: Session = Depends(get_db)):
    actor = _current_approver(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    rows = db.scalars(select(DataRequest).where(DataRequest.action == "PASSWORD_RESET", DataRequest.status == "PENDING").order_by(DataRequest.created_at.asc())).all()
    cards = []
    for row in rows:
        target = db.get(User, row.requester_id)
        if not target or not target.is_active or target.role == "SUPER_ADMIN":
            continue
        config = _parse_config(row)
        allowed = set(config.get("allowed_approvers", []))
        if actor.role not in allowed:
            continue
        cards.append(
            "<div class='request'><strong>Username:</strong> " + target.username +
            "<br><strong>Role:</strong> " + target.role +
            "<br><strong>Requested:</strong> " + str(row.created_at) +
            "<div class='actions'><form method='post' action='/password-reset-requests/approve'>" +
            f"<input type='hidden' name='request_id' value='{row.id}'><input type='hidden' name='csrf_token' value='{csrf_token(request)}'><button class='button' type='submit'>Approve</button></form>" +
            "<form method='post' action='/password-reset-requests/reject'>" +
            f"<input type='hidden' name='request_id' value='{row.id}'><input type='hidden' name='csrf_token' value='{csrf_token(request)}'><button class='button danger' type='submit'>Reject</button></form></div></div>"
        )
    if not cards:
        cards = ["<div class='ok'>No pending password recovery requests for your role.</div>"]
    body = "<h1>Password Recovery Requests</h1><p>Approve only requests you can independently verify. Approval never reveals the old password; it only opens a one-time password reset capability for the requester.</p>" + "".join(cards) + "<a class='back' href='/dashboard'>← Back to Dashboard</a>"
    return _page("Password Recovery Requests", body)


@router.post("/password-reset-requests/approve", dependencies=[Depends(require_csrf)])
def approve_password_reset(request: Request, request_id: int = Form(...), db: Session = Depends(get_db)):
    actor = _current_approver(request, db)
    row = db.get(DataRequest, request_id)
    if not actor or not row or row.action != "PASSWORD_RESET" or row.status != "PENDING":
        return RedirectResponse("/password-reset-requests", status_code=303)
    target = db.get(User, row.requester_id)
    config = _parse_config(row)
    allowed = set(config.get("allowed_approvers", []))
    if not target or not target.is_active or actor.role not in allowed:
        return RedirectResponse("/password-reset-requests", status_code=303)
    row.status = "APPROVED"
    row.decided_by_id = actor.id
    db.add(AuditEvent(actor_user_id=actor.id, action="PASSWORD_RESET_APPROVED", entity_type="User", entity_id=str(target.id), details=json.dumps({"request_id": row.id, "target_role": target.role})))
    db.commit()
    return RedirectResponse("/password-reset-requests", status_code=303)


@router.post("/password-reset-requests/reject", dependencies=[Depends(require_csrf)])
def reject_password_reset(request: Request, request_id: int = Form(...), db: Session = Depends(get_db)):
    actor = _current_approver(request, db)
    row = db.get(DataRequest, request_id)
    if not actor or not row or row.action != "PASSWORD_RESET" or row.status != "PENDING":
        return RedirectResponse("/password-reset-requests", status_code=303)
    target = db.get(User, row.requester_id)
    config = _parse_config(row)
    allowed = set(config.get("allowed_approvers", []))
    if not target or actor.role not in allowed:
        return RedirectResponse("/password-reset-requests", status_code=303)
    row.status = "REJECTED"
    row.decided_by_id = actor.id
    db.add(AuditEvent(actor_user_id=actor.id, action="PASSWORD_RESET_REJECTED", entity_type="User", entity_id=str(target.id), details=json.dumps({"request_id": row.id, "target_role": target.role})))
    db.commit()
    return RedirectResponse("/password-reset-requests", status_code=303)
