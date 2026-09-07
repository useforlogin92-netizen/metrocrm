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
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "error": error,
            "portal": portal,
            "super_admin_only": portal == "super_admin",
        },
    )


def _latest_approval_request(db: Session, user_id: int, portal: str | None = None):
    query = select(AuditEvent).where(
        AuditEvent.action == "LOGIN_APPROVAL_REQUEST",
        AuditEvent.entity_type == "User",
        AuditEvent.entity_id == str(user_id),
    ).order_by(AuditEvent.created_at.desc())
    rows = db.scalars(query.limit(20)).all()
    for row in rows:
        if not portal:
            return row
        try:
            details = json.loads(row.details or "{}")
        except Exception:
            details = {}
        if details.get("portal") == portal:
            return row
    return None


def _approval_decision_after(db: Session, user_id: int, request_id: int):
    rows = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "User",
            AuditEvent.entity_id == str(user_id),
            AuditEvent.action.in_(["LOGIN_APPROVAL_GRANTED", "LOGIN_APPROVAL_REJECTED"]),
            AuditEvent.id > request_id,
        )
        .order_by(AuditEvent.created_at.asc())
    ).all()
    return rows[0] if rows else None


def _approval_request_active(db: Session, user_id: int, request_id: int) -> tuple[bool, str]:
    request_event = db.get(AuditEvent, request_id)
    if not request_event or request_event.action != "LOGIN_APPROVAL_REQUEST" or request_event.entity_id != str(user_id):
        return False, "approval_request_not_found"
    if datetime.utcnow() - request_event.created_at > timedelta(seconds=APPROVAL_EXPIRY_SECONDS):
        return False, "approval_request_expired"
    latest = _latest_approval_request(db, user_id)
    if not latest or latest.id != request_id:
        return False, "approval_request_superseded"
    decision = _approval_decision_after(db, user_id, request_id)
    if decision:
        try:
            details = json.loads(decision.details or "{}")
        except Exception:
            details = {}
        return decision.action == "LOGIN_APPROVAL_GRANTED", details.get("reason", decision.action.lower())
    return False, "approval_pending"


def _login_flow(request: Request, username: str, password: str, method: str, portal: str, db: Session):
    user = db.scalar(select(User).where(User.username == username.strip()))
    required_role = {"admin": "ADMIN", "super_admin": "SUPER_ADMIN"}.get(portal)

    if required_role and (not user or user.role != required_role):
        label = "Admin" if required_role == "ADMIN" else "Super Admin"
        return _render(request, f"This portal is restricted to authorized {label} accounts." , portal), 403

    if not user or not authenticate_password(user, password):
        return _render(request, "Invalid username or password.", portal), 401

    if portal == "staff" and user.role in {"ADMIN", "SUPER_ADMIN"}:
        return _render(request, "Administrator accounts must use their dedicated secure login portal.", portal), 403

    methods = allowed_methods(user.role)
    if method not in methods:
        return _render(request, "This verification method is not allowed for your role.", portal), 403

    # Approval is intentionally selectable at every login. It is a per-login
    # Super Admin decision, not a permanent account approval flag.
    if method == "approval":
        latest = _latest_approval_request(db, user.id, portal)
        if latest and datetime.utcnow() - latest.created_at < timedelta(seconds=APPROVAL_RESEND_COOLDOWN_SECONDS):
            remaining = APPROVAL_RESEND_COOLDOWN_SECONDS - int((datetime.utcnow() - latest.created_at).total_seconds())
            return _render(request, f"Approval request already sent. You can resend it in about {max(1, remaining)} seconds.", portal), 429
        token, _ = create_pending(user, method)
        request_event = AuditEvent(
            actor_user_id=user.id,
            action="LOGIN_APPROVAL_REQUEST",
            entity_type="User",
            entity_id=str(user.id),
            details=json.dumps({"portal": portal, "role": user.role, "token": token}),
        )
        db.add(request_event)
        db.commit()
        request.session["pending_token"] = token
        request.session["approval_request_id"] = request_event.id
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "token": token,
                "method": "Super Admin Approval",
                "destination": "Waiting for Super Admin approval",
                "test_otp": None,
                "approval_pending": True,
                "approval_request_id": request_event.id,
                "approval_expiry_seconds": APPROVAL_EXPIRY_SECONDS,
                "approval_resend_seconds": APPROVAL_RESEND_COOLDOWN_SECONDS,
            },
        ), 200

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

    if method == "approval":
        request_id = request.session.get("approval_request_id")
        if not request_id:
            return JSONResponse({"error": "approval_request_missing"}, status_code=403)
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
    main_module._audit(db, user.id, "LOGIN_SUCCESS", user, {"method": method})
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/super-admin/login-requests", response_class=HTMLResponse)
def super_admin_login_requests(request: Request, db: Session = Depends(get_db)):
    actor = main_module._current_user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)

    rows = []
    requests = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.action == "LOGIN_APPROVAL_REQUEST", AuditEvent.entity_type == "User")
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
    ).all()
    seen_users = set()
    now = datetime.utcnow()
    for item in requests:
        if item.entity_id in seen_users:
            continue
        seen_users.add(item.entity_id)
        if now - item.created_at > timedelta(seconds=APPROVAL_EXPIRY_SECONDS):
            continue
        target = db.get(User, int(item.entity_id)) if item.entity_id else None
        if not target or not target.is_active or target.role == "SUPER_ADMIN":
            continue
        latest = _latest_approval_request(db, target.id)
        if not latest or latest.id != item.id:
            continue
        decision = _approval_decision_after(db, target.id, item.id)
        if decision:
            continue
        try:
            details = json.loads(item.details or "{}")
        except Exception:
            details = {}
        rows.append((item, target, details.get("portal", "staff")))

    html = """<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='10'><title>MetroCRM | Login Requests</title>
    <style>body{font-family:Inter,Arial,sans-serif;background:#f5f7fb;margin:0;padding:40px;color:#10213f}.wrap{max-width:980px;margin:auto}.card{background:#fff;border-radius:18px;padding:28px;box-shadow:0 8px 30px #0001}.head{display:flex;justify-content:space-between;align-items:center;gap:20px}.muted{color:#64748b}.row{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 0;border-top:1px solid #e5eaf2}.actions{display:flex;gap:8px}.btn{color:#fff;border:0;border-radius:9px;padding:10px 16px;font-weight:700;cursor:pointer}.approve{background:#16803c}.reject{background:#c62828}.empty{padding:35px 0;color:#64748b;text-align:center}.pill{display:inline-block;background:#edf5ff;color:#0758d8;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:700}</style></head><body><div class='wrap'><div class='card'>
    <div class='head'><div><h1>Admin / User Login Requests</h1><p class='muted'>Super Admin approval requests · approval window: 15 minutes · auto-refresh: 10 seconds.</p></div><a href='/dashboard'>Dashboard</a></div>"""
    if not rows:
        html += "<div class='empty'>No pending login approval requests.</div>"
    for item, target, portal in rows:
        age = max(0, int((now - item.created_at).total_seconds()))
        remaining = max(0, APPROVAL_EXPIRY_SECONDS - age)
        html += f"<div class='row'><div><strong>{target.username}</strong><div class='muted'>Role: {target.role} · Portal: <span class='pill'>{portal}</span> · Requested: {item.created_at} · Expires in about {remaining//60}m {remaining%60}s</div></div><div class='actions'><form method='post' action='/super-admin/login-requests/{item.id}/approve'><button class='btn approve'>Approve</button></form><form method='post' action='/super-admin/login-requests/{item.id}/reject'><button class='btn reject'>Reject</button></form></div></div>"
    html += "</div></div></body></html>"
    return HTMLResponse(html)


@app.post("/super-admin/login-requests/{request_id}/approve")
def approve_login_request(request_id: int, request: Request, db: Session = Depends(get_db)):
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
    latest = _latest_approval_request(db, target.id)
    if not latest or latest.id != request_id:
        return HTMLResponse("This request has been superseded by a newer request.", status_code=409)
    if datetime.utcnow() - event.created_at > timedelta(seconds=APPROVAL_EXPIRY_SECONDS):
        return HTMLResponse("This approval request has expired. The user must send a new request.", status_code=410)
    if _approval_decision_after(db, target.id, request_id):
        return HTMLResponse("This request has already been decided.", status_code=409)
    main_module._audit(db, actor.id, "LOGIN_APPROVAL_GRANTED", target, {"request_id": request_id, "portal": "login_approval", "reason": "approved_by_super_admin"})
    db.commit()
    return RedirectResponse("/super-admin/login-requests", status_code=303)


@app.post("/super-admin/login-requests/{request_id}/reject")
def reject_login_request(request_id: int, request: Request, db: Session = Depends(get_db)):
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
    latest = _latest_approval_request(db, target.id)
    if not latest or latest.id != request_id:
        return HTMLResponse("This request has been superseded by a newer request.", status_code=409)
    if _approval_decision_after(db, target.id, request_id):
        return HTMLResponse("This request has already been decided.", status_code=409)
    main_module._audit(db, actor.id, "LOGIN_APPROVAL_REJECTED", target, {"request_id": request_id, "reason": "rejected_by_super_admin"})
    db.commit()
    return RedirectResponse("/super-admin/login-requests", status_code=303)


# Put the guarded routes before the legacy routes registered in app.main.
def _move_first(path: str, method: str):
    for idx, route in enumerate(app.router.routes):
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            app.router.routes.insert(0, app.router.routes.pop(idx))
            return

_move_first("/auth/login", "POST")
_move_first("/auth/verify", "POST")
