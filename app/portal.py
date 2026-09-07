from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main as main_module
from app.auth import allowed_methods, authenticate_password, create_pending
from app.database import get_db
from app.email_verification import EmailVerification
from app.models import User
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
        return _render(request, f"This portal is restricted to authorized {label} accounts." , portal), 403

    if not user or not authenticate_password(user, password):
        return _render(request, "Invalid username or password.", portal), 401

    if portal == "staff" and user.role in {"ADMIN", "SUPER_ADMIN"}:
        return _render(request, "Administrator accounts must use their dedicated secure login portal.", portal), 403

    methods = allowed_methods(user.role)
    if method not in methods:
        return _render(request, "This verification method is not allowed for your role.", portal), 403

    email_verified = db.scalar(
        select(EmailVerification.id).where(EmailVerification.user_id == user.id)
    ) is not None

    if method == "email_otp" and not user.email:
        return _render(request, "No registered email is available for this account.", portal), 400

    if method != "email_otp" and not (user.is_approved or email_verified):
        return _render(request, "Account access requires either email verification or administrator approval.", portal), 403

    if method == "approval" and not user.is_approved:
        return _render(request, "Administrator approval has not been granted.", portal), 403

    if method in {"mobile_otp", "email_otp"}:
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
            {
                "request": request,
                "token": token,
                "method": "Security Question",
                "destination": user.security_question,
                "test_otp": None,
            },
        ), 200

    if method == "approval":
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "token": token,
                "method": "Administrator Approval",
                "destination": "approved account",
                "test_otp": "APPROVED" if main_module.settings.environment != "production" else None,
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
