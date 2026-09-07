from datetime import datetime, timedelta
import json

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main as main_module
from app.auth import allowed_methods, authenticate_password, create_pending, pending_method, verify_pending
from app.config import settings
from app.database import get_db
from app.email_verification import EmailVerification
from app.models import AuditEvent, User
from app.services.integrations import generate_and_send_otp

app = main_module.app
templates = main_module.templates

APPROVAL_EXPIRY_SECONDS = 15 * 60
APPROVAL_RESEND_COOLDOWN_SECONDS = 60


def _render(request: Request, error: str | None, portal: str):
    template_name = "admin_login.html" if portal == "admin" else "login.html"
    return templates.TemplateResponse(template_name, {"request": request, "error": error, "portal": portal, "super_admin_only": portal == "super_admin"})


def _approval_details(event: AuditEvent) -> dict:
    try:
        details = json.loads(event.details or "{}")
        return details if isinstance(details, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _latest_approval_request(db: Session, user_id: int, portal: str | None = None):
    query = select(AuditEvent).where(AuditEvent.action == "LOGIN_APPROVAL_REQUEST", AuditEvent.entity_type == "User", AuditEvent.entity_id == str(user_id)).order_by(AuditEvent.id.desc())
    for row in db.scalars(query.limit(100)).all():
        if portal is None or _approval_details(row).get("portal") == portal:
            return row
    return None


def _approval_decision_after(db: Session, user_id: int, request_id: int):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "User", AuditEvent.entity_id == str(user_id), AuditEvent.action.in_(["LOGIN_APPROVAL_GRANTED", "LOGIN_APPROVAL_REJECTED"]), AuditEvent.id > request_id).order_by(AuditEvent.id.asc())).all()
    for row in rows:
        if str(_approval_details(row).get("request_id", "")) == str(request_id):
            return row
    return None


def _approval_request_age(event: AuditEvent) -> float:
    if event.created_at is None:
        return float("inf")
    created_at = event.created_at.replace(tzinfo=None) if event.created_at.tzinfo is not None else event.created_at
    return max(0.0, (datetime.utcnow() - created_at).total_seconds())


def _approval_request_active(db: Session, user_id: int, request_id: int) -> tuple[bool, str]:
    request_event = db.get(AuditEvent, request_id)
    if not request_event or request_event.action != "LOGIN_APPROVAL_REQUEST" or request_event.entity_id != str(user_id):
        return False, "approval_request_not_found"
    if _approval_request_age(request_event) > APPROVAL_EXPIRY_SECONDS:
        return False, "approval_request_expired"
    portal = _approval_details(request_event).get("portal")
    latest = _latest_approval_request(db, user_id, portal)
    if not latest or latest.id != request_id:
        return False, "approval_request_superseded"
    decision = _approval_decision_after(db, user_id, request_id)
    if decision:
        return decision.action == "LOGIN_APPROVAL_GRANTED", _approval_details(decision).get("reason", decision.action.lower())
    return False, "approval_pending"


def _login_flow(request: Request, username: str, password: str, method: str, portal: str, db: Session):
    user = db.scalar(select(User).where(User.username == username.strip()))
    required_role = {"admin": "ADMIN", "super_admin": "SUPER_ADMIN"}.get(portal)
    if required_role and (not user or user.role != required_role):
        label = "Admin" if required_role == "ADMIN" else "Super Admin"
        return _render(request, f"This portal is restricted to authorized {label} accounts.", portal), 403
    if not user or not authenticate_password(user, password):
        return _render(request, "Invalid username or password.", portal), 401
    if portal == "staff" and user.role in {"ADMIN", "SUPER_ADMIN"}:
        return _render(request, "Administrator accounts must use their dedicated secure login portal.", portal), 403
    if method not in allowed_methods(user.role):
        return _render(request, "This verification method is not allowed for your role.", portal), 403

    if method == "approval":
        latest = _latest_approval_request(db, user.id, portal)
        if latest and _approval_request_age(latest) < APPROVAL_RESEND_COOLDOWN_SECONDS:
            remaining = APPROVAL_RESEND_COOLDOWN_SECONDS - int(_approval_request_age(latest))
            return _render(request, f"Approval request already sent. You can resend it in about {max(1, remaining)} seconds.", portal), 429
        token, _ = create_pending(user, method)
        request_event = AuditEvent(actor_user_id=user.id, action="LOGIN_APPROVAL_REQUEST", entity_type="User", entity_id=str(user.id), details=json.dumps({"portal": portal, "role": user.role}))
        db.add(request_event)
        db.flush()
        db.commit()
        request.session["pending_token"] = token
        request.session["approval_request_id"] = request_event.id
        request.session["login_portal"] = portal
        return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": "Super Admin Approval", "destination": "Waiting for Super Admin approval", "test_otp": None, "approval_pending": True, "approval_request_id": request_event.id, "approval_expiry_seconds": APPROVAL_EXPIRY_SECONDS, "approval_resend_seconds": APPROVAL_RESEND_COOLDOWN_SECONDS}), 200

    email_verified = db.scalar(select(EmailVerification.id).where(EmailVerification.user_id == user.id)) is not None
    if method == "email_otp" and not user.email:
        return _render(request, "No registered email is available for this account.", portal), 400
    if method != "email_otp" and not (user.is_approved or email_verified):
        return _render(request, "Account access requires either email verification or administrator approval.", portal), 403
    if method in {"mobile_otp", "email_otp"}:
        destination_value = user.mobile if method == "mobile_otp" else user.email
        if not destination_value:
            label = "mobile" if method == "mobile_otp" else "email"
            return _render(request, f"No registered {label} is available for this account.", portal), 400
        try:
            otp, _ = generate_and_send_otp("mobile" if method == "mobile_otp" else "email", destination_value)
        except RuntimeError as exc:
            main_module._audit(db, user.id, "OTP_DELIVERY_FAILED", user, {"error": str(exc)})
            db.commit()
            return _render(request, "OTP delivery is not configured. Contact the administrator.", portal), 503
        token, _ = create_pending(user, method, otp=otp)
    else:
        token, _ = create_pending(user, method)
    request.session["pending_token"] = token
    request.session["login_portal"] = portal
    destination = "registered mobile" if method == "mobile_otp" else "registered email" if method == "email_otp" else None
    if method == "security_question":
        return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": "Security Question", "destination": user.security_question, "test_otp": None}), 200
    return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": method.replace("_", " ").title(), "destination": destination, "test_otp": otp if settings.environment != "production" else None, "approval_pending": False}), 200


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return _render(request, None, "admin")


@app.post("/auth/admin/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...), method: str = Form(...), db: Session = Depends(get_db)):
    response, _ = _login_flow(request, username, password, method, "admin", db)
    return response


@app.post("/auth/login")
def staff_login(request: Request, username: str = Form(...), password: str = Form(...), method: str = Form(...), portal: str = Form(""), db: Session = Depends(get_db)):
    response, _ = _login_flow(request, username, password, method, "staff", db)
    return response


@app.post("/auth/verify")
def portal_verify(request: Request, token: str = Form(...), value: str = Form(...), db: Session = Depends(get_db)):
    method = pending_method(token)
    if not method:
        return JSONResponse({"error": "verification_expired_or_invalid"}, status_code=401)
    expiry = APPROVAL_EXPIRY_SECONDS if method == "approval" else settings.otp_expiry_seconds
    user_id = verify_pending(token, value.strip(), expiry, settings.otp_max_attempts)
    if not user_id:
        if method == "approval":
            return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": "Super Admin Approval", "destination": "Approval request expired or invalid. Start a new request.", "test_otp": None, "approval_pending": False, "error": "Approval request expired or invalid."}, status_code=401)
        return JSONResponse({"error": "verification_failed"}, status_code=401)
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return JSONResponse({"error": "account_disabled"}, status_code=403)
    login_portal = request.session.get("login_portal")
    if method == "approval":
        request_id = request.session.get("approval_request_id")
        if not request_id or login_portal not in {"admin", "staff"}:
            return JSONResponse({"error": "approval_request_missing"}, status_code=403)
        if login_portal == "admin" and user.role != "ADMIN":
            return JSONResponse({"error": "approval_portal_role_mismatch"}, status_code=403)
        if login_portal == "staff" and user.role in {"ADMIN", "SUPER_ADMIN"}:
            return JSONResponse({"error": "administrator_must_use_dedicated_portal"}, status_code=403)
        allowed, reason = _approval_request_active(db, user.id, int(request_id))
        if not allowed:
            return JSONResponse({"error": reason}, status_code=403)
    elif method != "email_otp":
        verified = db.scalar(select(EmailVerification.id).where(EmailVerification.user_id == user.id)) is not None
        if not (user.is_approved or verified):
            return JSONResponse({"error": "account_not_approved"}, status_code=403)
    if method == "email_otp":
        existing = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id))
        if existing is None:
            db.add(EmailVerification(user_id=user.id, verified_at=datetime.utcnow()))
        else:
            existing.verified_at = datetime.utcnow()
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["session_version"] = user.session_version
    request.session["login_portal"] = login_portal or "staff"
    main_module._audit(db, user.id, "LOGIN_SUCCESS", user, {"method": method, "portal": login_portal})
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/super-admin/login-requests", response_class=HTMLResponse)
def super_admin_login_requests(request: Request, db: Session = Depends(get_db)):
    actor = main_module._current_user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    candidates = db.scalars(select(AuditEvent).where(AuditEvent.action == "LOGIN_APPROVAL_REQUEST", AuditEvent.entity_type == "User").order_by(AuditEvent.id.desc()).limit(500)).all()
    latest_by_user: dict[str, AuditEvent] = {}
    for item in candidates:
        if item.entity_id and item.entity_id not in latest_by_user:
            latest_by_user[item.entity_id] = item
    rows = []
    for item in latest_by_user.values():
        if _approval_request_age(item) > APPROVAL_EXPIRY_SECONDS:
            continue
        target = db.get(User, int(item.entity_id)) if item.entity_id and item.entity_id.isdigit() else None
        if not target or not target.is_active or target.role == "SUPER_ADMIN":
            continue
        if _approval_decision_after(db, target.id, item.id):
            continue
        details = _approval_details(item)
        portal = details.get("portal", "staff")
        if portal == "super_admin":
            continue
        rows.append((item, target, portal))
    html = """<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='10'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | Login Requests</title><style>body{font-family:Inter,Arial,sans-serif;background:#f5f7fb;margin:0;padding:40px;color:#10213f}.wrap{max-width:980px;margin:auto}.card{background:#fff;border-radius:18px;padding:28px;box-shadow:0 8px 30px #0001}.head{display:flex;justify-content:space-between;align-items:center;gap:20px}.muted{color:#64748b}.row{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 0;border-top:1px solid #e5eaf2}.actions{display:flex;gap:8px}.btn{color:#fff;border:0;border-radius:9px;padding:10px 16px;font-weight:700;cursor:pointer}.approve{background:#16803c}.reject{background:#c62828}.empty{padding:35px 0;color:#64748b;text-align:center}.pill{display:inline-block;background:#edf5ff;color:#0758d8;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:700}@media(max-width:700px){body{padding:16px}.card{padding:18px}.row{display:block}.actions{margin-top:14px}}</style></head><body><div class='wrap'><div class='card'><div class='head'><div><h1>Admin / User Login Requests</h1><p class='muted'>Super Admin approval requests · approval window: 15 minutes · auto-refresh: 10 seconds.</p></div><a href='/dashboard'>Dashboard</a></div>"""
    if not rows:
        html += "<div class='empty'>No pending login approval requests.</div>"
    for item, target, portal in rows:
        remaining = max(0, APPROVAL_EXPIRY_SECONDS - int(_approval_request_age(item)))
        html += f"<div class='row'><div><strong>{target.username}</strong><div class='muted'>Role: {target.role} · Portal: <span class='pill'>{portal}</span> · Requested: {item.created_at} · Expires in about {remaining//60}m {remaining%60}s</div></div><div class='actions'><form method='post' action='/super-admin/login-requests/{item.id}/approve'><button class='btn approve'>Approve</button></form><form method='post' action='/super-admin/login-requests/{item.id}/reject'><button class='btn reject'>Reject</button></form></div></div>"
    html += "</div></div></body></html>"
    return HTMLResponse(html)


def _decide_login_request(request_id: int, request: Request, db: Session, action: str):
    actor = main_module._current_user(request, db)
    event = db.get(AuditEvent, request_id)
    if not actor or actor.role != "SUPER_ADMIN" or not event or event.action != "LOGIN_APPROVAL_REQUEST":
        return HTMLResponse("Not permitted", status_code=403)
    try:
        user_id = int(event.entity_id)
    except (TypeError, ValueError):
        return HTMLResponse("Invalid request", status_code=400)
    target = db.get(User, user_id)
    if not target or not target.is_active or target.role == "SUPER_ADMIN":
        return HTMLResponse("Invalid target", status_code=400)
    if _approval_request_age(event) > APPROVAL_EXPIRY_SECONDS:
        return HTMLResponse("This approval request has expired. The user must send a new request.", status_code=410)
    latest = _latest_approval_request(db, target.id)
    if not latest or latest.id != request_id:
        return HTMLResponse("This request has been superseded by a newer request.", status_code=409)
    if _approval_decision_after(db, target.id, request_id):
        return HTMLResponse("This request has already been decided.", status_code=409)
    portal = _approval_details(event).get("portal", "staff")
    decision_action = "LOGIN_APPROVAL_GRANTED" if action == "approve" else "LOGIN_APPROVAL_REJECTED"
    reason = "approved_by_super_admin" if action == "approve" else "rejected_by_super_admin"
    main_module._audit(db, actor.id, decision_action, target, {"request_id": request_id, "portal": portal, "reason": reason})
    db.commit()
    return RedirectResponse("/super-admin/login-requests", status_code=303)


@app.post("/super-admin/login-requests/{request_id}/approve")
def approve_login_request(request_id: int, request: Request, db: Session = Depends(get_db)):
    return _decide_login_request(request_id, request, db, "approve")


@app.post("/super-admin/login-requests/{request_id}/reject")
def reject_login_request(request_id: int, request: Request, db: Session = Depends(get_db)):
    return _decide_login_request(request_id, request, db, "reject")


# Put the guarded routes before the legacy routes registered in app.main.
def _move_first(path: str, method: str):
    for idx, route in enumerate(app.router.routes):
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            app.router.routes.insert(0, app.router.routes.pop(idx))
            return


_move_first("/auth/login", "POST")
_move_first("/auth/verify", "POST")
