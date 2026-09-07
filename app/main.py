from datetime import datetime
import json

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import allowed_methods, authenticate_password, create_pending, pending_method, verify_pending
from app.config import settings
from app.database import Base, engine, get_db
from app.email_verification import EmailVerification
from app.models import AuditEvent, User
from app.security import hash_password
from app.routers.catalog_sharing import router as catalog_sharing_router
from app.routers.caller_search import router as caller_search_router
from app.routers.backups import router as backups_router
from app.routers.integrations import router as integrations_router
from app.services.backup_scheduler import start_backup_scheduler, stop_backup_scheduler
from app.services.integrations import generate_and_send_otp
import app.models  # noqa: F401
import app.catalog_models  # noqa: F401
import app.integration_models  # noqa: F401
import app.email_verification  # noqa: F401

app = FastAPI(title="MetroCRM", version="0.3.0")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=settings.session_max_age, https_only=settings.environment == "production", same_site="lax")
templates = Jinja2Templates(directory="app/templates")
app.include_router(catalog_sharing_router)
app.include_router(caller_search_router)
app.include_router(backups_router)
app.include_router(integrations_router)

@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    start_backup_scheduler()

@app.on_event("shutdown")
def shutdown() -> None:
    stop_backup_scheduler()

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/setup", response_class=HTMLResponse)
def setup_page(db: Session = Depends(get_db)):
    if db.scalar(select(User.id).limit(1)) is not None:
        return HTMLResponse("Setup has already been completed.", status_code=409)
    return HTMLResponse("""
    <!doctype html><html><head><title>MetroCRM Initial Setup</title>
    <style>body{font-family:Arial,sans-serif;background:#f5f7fb;display:flex;justify-content:center;padding:40px}.card{background:white;padding:28px;border-radius:12px;width:420px;box-shadow:0 4px 18px #0001}label{display:block;margin-top:14px;font-weight:600}input{width:100%;box-sizing:border-box;padding:10px;margin-top:6px;border:1px solid #bbb;border-radius:6px}button{width:100%;padding:12px;margin-top:22px;background:#2878e8;color:white;border:0;border-radius:6px;font-weight:600}</style>
    </head><body><div class="card"><h1>MetroCRM</h1><p>Create the first Super Admin account.</p>
    <form method="post" action="/auth/setup">
    <label>Username</label><input name="username" required autocomplete="username">
    <label>Password</label><input name="password" type="password" required minlength="8" autocomplete="new-password">
    <label>Security Question</label><input name="security_question" required>
    <label>Security Answer</label><input name="security_answer" type="password" required autocomplete="off">
    <input type="hidden" name="role" value="SUPER_ADMIN">
    <button type="submit">Create Super Admin</button></form></div></body></html>
    """)

@app.post("/auth/setup")
def setup(username: str = Form(...), password: str = Form(...), role: str = Form("SUPER_ADMIN"), security_question: str = Form(""), security_answer: str = Form(""), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).limit(1)) is not None:
        return JSONResponse({"error": "setup_already_completed"}, status_code=409)
    role = role.upper()
    if role != "SUPER_ADMIN":
        return JSONResponse({"error": "first_setup_must_create_super_admin"}, status_code=400)
    if not security_question.strip() or not security_answer.strip():
        return JSONResponse({"error": "super_admin_security_question_required"}, status_code=400)
    user = User(username=username.strip(), password_hash=hash_password(password), role=role, security_question=security_question.strip(), security_answer_hash=hash_password(security_answer.strip()), is_active=True, is_approved=True)
    db.add(user); db.commit()
    return RedirectResponse("/", status_code=303)

def _current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active or user.session_version != request.session.get("session_version"):
        return None
    return user

def _can_approve(actor: User, target: User) -> bool:
    if actor.id == target.id:
        return False
    if actor.role == "SUPER_ADMIN":
        return target.role != "SUPER_ADMIN"
    if actor.role == "ADMIN":
        return target.role not in {"SUPER_ADMIN", "ADMIN"}
    return False

@app.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), method: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not authenticate_password(user, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."}, status_code=401)
    methods = allowed_methods(user.role)
    if method not in methods:
        return templates.TemplateResponse("login.html", {"request": request, "error": "This verification method is not allowed for your role."}, status_code=403)

    email_verified = db.scalar(select(EmailVerification.id).where(EmailVerification.user_id == user.id)) is not None
    if method == "email_otp":
        if not user.email:
            return templates.TemplateResponse("login.html", {"request": request, "error": "No registered email is available for this account."}, status_code=400)
    elif not (user.is_approved or email_verified):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Account access requires either email verification or administrator approval."}, status_code=403)
    elif method == "approval" and not user.is_approved:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Administrator approval has not been granted."}, status_code=403)

    if method in {"mobile_otp", "email_otp"}:
        destination_value = user.mobile if method == "mobile_otp" else user.email
        if not destination_value:
            return templates.TemplateResponse("login.html", {"request": request, "error": f"No registered {('mobile' if method == 'mobile_otp' else 'email')} is available for this account."}, status_code=400)
        try:
            otp, delivery = generate_and_send_otp("mobile" if method == "mobile_otp" else "email", destination_value)
        except RuntimeError as exc:
            db.add(AuditEvent(actor_user_id=user.id, action="OTP_DELIVERY_FAILED", entity_type="User", entity_id=str(user.id), details=str(exc)))
            db.commit()
            return templates.TemplateResponse("login.html", {"request": request, "error": "OTP delivery is not configured. Contact the administrator."}, status_code=503)
        token, _ = create_pending(user, method, otp=otp)
    else:
        token, _ = create_pending(user, method)
    request.session["pending_token"] = token
    destination = "registered mobile" if method == "mobile_otp" else "registered email" if method == "email_otp" else None
    if method == "security_question":
        return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": "Security Question", "destination": user.security_question, "test_otp": None})
    if method == "approval":
        return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": "Administrator Approval", "destination": "approved account", "test_otp": "APPROVED" if settings.environment != "production" else None})
    return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": method.replace("_", " ").title(), "destination": destination, "test_otp": otp if settings.environment != "production" else None})

@app.post("/auth/verify")
def verify(request: Request, token: str = Form(...), value: str = Form(...), db: Session = Depends(get_db)):
    method = pending_method(token)
    user_id = verify_pending(token, value.strip(), settings.otp_expiry_seconds, settings.otp_max_attempts)
    if not user_id:
        return JSONResponse({"error": "verification_failed"}, status_code=401)
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return JSONResponse({"error": "account_disabled"}, status_code=403)
    if method != "email_otp" and not (user.is_approved or db.scalar(select(EmailVerification.id).where(EmailVerification.user_id == user.id)) is not None):
        return JSONResponse({"error": "account_not_approved"}, status_code=403)
    if method == "approval" and not user.is_approved:
        return JSONResponse({"error": "approval_revoked"}, status_code=403)
    if method == "email_otp":
        existing = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id))
        if existing is None:
            db.add(EmailVerification(user_id=user.id, verified_at=datetime.utcnow()))
        else:
            existing.verified_at = datetime.utcnow()
    request.session.clear(); request.session["user_id"] = user.id; request.session["session_version"] = user.session_version
    db.add(AuditEvent(actor_user_id=user.id, action="LOGIN_SUCCESS", entity_type="User", entity_id=str(user.id), details=json.dumps({"method": method}))); db.commit()
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/admin/users/pending")
def pending_users(request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="administrator_required")
    users = db.scalars(select(User).where(User.is_active.is_(True), User.is_approved.is_(False)).order_by(User.created_at)).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "email": u.email, "created_at": u.created_at.isoformat() if u.created_at else None} for u in users]

@app.post("/admin/users/{user_id}/approve")
def approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if not _can_approve(actor, target):
        return JSONResponse({"error": "approval_not_permitted"}, status_code=403)
    target.is_approved = True
    db.add(AuditEvent(actor_user_id=actor.id, action="USER_APPROVED", entity_type="User", entity_id=str(target.id), details=json.dumps({"target_role": target.role})))
    db.commit()
    return {"status": "approved", "user_id": target.id}

@app.post("/admin/users/{user_id}/revoke-approval")
def revoke_user_approval(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if not _can_approve(actor, target):
        return JSONResponse({"error": "approval_not_permitted"}, status_code=403)
    target.is_approved = False
    target.session_version += 1
    db.add(AuditEvent(actor_user_id=actor.id, action="USER_APPROVAL_REVOKED", entity_type="User", entity_id=str(target.id), details=json.dumps({"target_role": target.role})))
    db.commit()
    return {"status": "approval_revoked", "user_id": target.id}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": user.username,
        "role": user.role,
        "avatar": user.username[:1].upper(),
        "show_integrations": user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"},
        "show_alerts": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_approvals": user.role in {"SUPER_ADMIN", "ADMIN"},
    })

@app.get("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
