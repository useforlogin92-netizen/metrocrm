from datetime import datetime

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main as main_module
from app.auth import allowed_methods, authenticate_password, create_pending
from app.database import get_db
from app.email_verification import EmailVerification
from app.models import AuditEvent, User
from app.services.integrations import generate_and_send_otp

app = main_module.app
templates = main_module.templates


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

    methods = allowed_methods(user.role)
    if method not in methods:
        return _render(request, "This verification method is not allowed for your role.", portal), 403

    # Admin OTP/email-OTP integrations are not enabled yet. Keep the backend
    # ready for them, but the current Admin portal uses approval only.
    if portal == "admin" and method != "approval":
        return _render(request, "Admin OTP verification is not enabled yet. Use Super Admin approval.", portal), 400

    email_verified = db.scalar(
        select(EmailVerification.id).where(EmailVerification.user_id == user.id)
    ) is not None

    if method == "email_otp" and not user.email:
        return _render(request, "No registered email is available for this account.", portal), 400

    if method != "email_otp" and method != "approval" and not (user.is_approved or email_verified):
        return _render(request, "Account access requires either email verification or administrator approval.", portal), 403

    if method == "approval":
        # Do not block an unapproved Admin here: this is the point where the
        # login request is created and delivered to Super Admin for approval.
        token, _ = create_pending(user, method)
        main_module._audit(
            db,
            user.id,
            "LOGIN_APPROVAL_REQUEST",
            user,
            {"portal": portal, "role": user.role, "requested_at": datetime.utcnow().isoformat()},
        )
        db.commit()
    elif method in {"mobile_otp", "email_otp"}:
        destination_value = user.mobile if method == "mobile_otp" else user.email
        if not destination_value:
            label = "mobile" if method == "mobile_otp" else "email"
            return _render(request, f"No registered {label} is available for this account.", portal), 400
        try:
            otp, _ = generate_and_send_otp(
                "mobile" if method == "mobile_otp" else "email",
                destination_value,
            )
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
        return templates.TemplateResponse(
            "verify.html",
            {"request": request, "token": token, "method": "Security Question", "destination": user.security_question, "test_otp": None},
        ), 200

    if method == "approval":
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "token": token,
                "method": "Administrator Approval",
                "destination": "Waiting for Super Admin approval",
                "test_otp": None,
                "approval_pending": not user.is_approved,
            },
        ), 200

    return templates.TemplateResponse(
        "verify.html",
        {
            "request": request,
            "token": token,
            "method": method.replace("_", " ").title(),
            "destination": destination,
            "test_otp": otp if main_module.settings.environment != "production" else None,
            "approval_pending": False,
        },
    ), 200


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return _render(request, None, "admin")


@app.post("/auth/admin/login")
def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    method: str = Form(...),
    db: Session = Depends(get_db),
):
    response, _ = _login_flow(request, username, password, method, "admin", db)
    return response


@app.get("/super-admin/login-requests", response_class=HTMLResponse)
def super_admin_login_requests(request: Request, db: Session = Depends(get_db)):
    actor = main_module._current_user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    requests = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.action == "LOGIN_APPROVAL_REQUEST")
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    ).all()
    rows = []
    for item in requests:
        target = db.get(User, int(item.entity_id)) if item.entity_id else None
        if target and target.is_active and target.role == "ADMIN" and not target.is_approved:
            rows.append((item, target))
    html = """<!doctype html><html><head><meta charset='utf-8'><title>MetroCRM | Login Requests</title>
    <style>body{font-family:Arial,sans-serif;background:#f5f7fb;margin:0;padding:40px;color:#10213f}.wrap{max-width:900px;margin:auto}.card{background:#fff;border-radius:16px;padding:24px;box-shadow:0 8px 30px #0001}.head{display:flex;justify-content:space-between;align-items:center;gap:20px}.muted{color:#64748b}.row{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 0;border-top:1px solid #e5eaf2}.btn{background:#1677ff;color:#fff;border:0;border-radius:9px;padding:10px 16px;font-weight:700;cursor:pointer}.empty{padding:30px 0;color:#64748b}</style></head><body><div class='wrap'><div class='card'>
    <div class='head'><div><h1>Admin Login Requests</h1><p class='muted'>Pending Admin accounts waiting for Super Admin approval.</p></div><a href='/dashboard'>Dashboard</a></div>"""
    if not rows:
        html += "<div class='empty'>No pending Admin login requests.</div>"
    for item, target in rows:
        html += f"<div class='row'><div><strong>{target.username}</strong><div class='muted'>Role: ADMIN · Request: {item.created_at}</div></div><form method='post' action='/super-admin/login-requests/{target.id}/approve'><button class='btn'>Approve Login</button></form></div>"
    html += "</div></div></body></html>"
    return HTMLResponse(html)


@app.post("/super-admin/login-requests/{user_id}/approve")
def approve_login_request(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = main_module._current_user(request, db)
    target = db.get(User, user_id)
    if not actor or actor.role != "SUPER_ADMIN" or not target or target.role != "ADMIN":
        return HTMLResponse("Not permitted", status_code=403)
    target.is_approved = True
    main_module._audit(db, actor.id, "LOGIN_APPROVAL_GRANTED", target, {"portal": "admin"})
    db.commit()
    return RedirectResponse("/super-admin/login-requests", status_code=303)


@app.post("/auth/login")
def staff_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    method: str = Form(...),
    portal: str = Form(""),
    db: Session = Depends(get_db),
):
    response, _ = _login_flow(request, username, password, method, "staff", db)
    return response


# The legacy /auth/login route already exists in app.main. FastAPI uses the
# first matching route, so place the guarded staff route before that legacy route.
_new_route = app.router.routes.pop()
for _idx, _route in enumerate(app.router.routes):
    if getattr(_route, "path", None) == "/auth/login" and "POST" in getattr(_route, "methods", set()):
        app.router.routes.insert(_idx, _new_route)
        break
else:
    app.router.routes.append(_new_route)
