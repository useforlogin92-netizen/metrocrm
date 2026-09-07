from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import time

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import allowed_methods, authenticate_password, create_pending, pending_method, verify_pending
from app.config import settings
from app.csrf import csrf_token, require_csrf
from app.database import Base, engine, get_db
from app.email_verification import EmailVerification
from app.models import AuditEvent, User
from app.permissions import Access, Role
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

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_backup_scheduler()
    try:
        yield
    finally:
        stop_backup_scheduler()


app = FastAPI(title="MetroCRM", version="0.4.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=settings.session_max_age, https_only=settings.environment == "production", same_site="lax")
templates = Jinja2Templates(directory="app/templates")
app.include_router(catalog_sharing_router)
app.include_router(caller_search_router)
app.include_router(backups_router)
app.include_router(integrations_router)

_super_admin_failures: dict[str, list[float]] = {}
_SUPER_ADMIN_MAX_FAILURES = 5
_SUPER_ADMIN_WINDOW_SECONDS = 15 * 60


def _super_admin_rate_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


def _super_admin_rate_limited(request: Request, username: str) -> bool:
    now = time.time()
    key = _super_admin_rate_key(request, username)
    attempts = [t for t in _super_admin_failures.get(key, []) if now - t < _SUPER_ADMIN_WINDOW_SECONDS]
    _super_admin_failures[key] = attempts
    return len(attempts) >= _SUPER_ADMIN_MAX_FAILURES


def _record_super_admin_failure(request: Request, username: str) -> None:
    now = time.time()
    key = _super_admin_rate_key(request, username)
    attempts = [t for t in _super_admin_failures.get(key, []) if now - t < _SUPER_ADMIN_WINDOW_SECONDS]
    attempts.append(now)
    _super_admin_failures[key] = attempts


def _clear_super_admin_failures(request: Request, username: str) -> None:
    _super_admin_failures.pop(_super_admin_rate_key(request, username), None)


def _json_object(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _can_manage_user(actor: User, target: User | None = None, target_role: str | None = None) -> bool:
    role = actor.role.upper()
    wanted = (target_role or (target.role if target else "")).upper()
    if wanted not in {r.value for r in Role}:
        return False
    if role == "SUPER_ADMIN":
        return not (target and target.id == actor.id and wanted != "SUPER_ADMIN")
    if role == "ADMIN":
        if target and target.role.upper() in {"SUPER_ADMIN", "ADMIN"}:
            return False
        return wanted not in {"SUPER_ADMIN", "ADMIN"}
    return False


def _valid_reporting_manager(actor: User, manager_id: int | None, target: User | None, db: Session) -> bool:
    if manager_id is None:
        return True
    if target and manager_id == target.id:
        return False
    manager = db.get(User, manager_id)
    if not manager or not manager.is_active:
        return False
    if manager.role.upper() not in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}:
        return False
    if actor.role.upper() == "ADMIN" and manager.role.upper() == "SUPER_ADMIN":
        return False
    return True


def _audit(db: Session, actor_id: int | None, action: str, target: User | None = None, details: dict | None = None) -> None:
    db.add(AuditEvent(actor_user_id=actor_id, action=action, entity_type="User" if target else None, entity_id=str(target.id) if target else None, details=json.dumps(details or {})))


def _browser_redirect(request: Request, location: str, fallback: dict | None = None, status_code: int = 303):
    accept = request.headers.get("accept", "")
    if "text/html" in accept or "*/*" in accept:
        return RedirectResponse(location, status_code=status_code)
    return JSONResponse(fallback or {"status": "ok"})


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "super_admin_only": False})


@app.get("/super-admin/login", response_class=HTMLResponse)
def super_admin_login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "super_admin_only": True})


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
    <label>Mobile (optional)</label><input name="mobile" autocomplete="tel">
    <label>Email (optional)</label><input name="email" type="email" autocomplete="email">
    <label>Security Question</label><input name="security_question" required>
    <label>Security Answer</label><input name="security_answer" type="password" required autocomplete="off">
    <input type="hidden" name="role" value="SUPER_ADMIN">
    <button type="submit">Create Super Admin</button></form></div></body></html>
    """)


@app.post("/auth/setup")
def setup(username: str = Form(...), password: str = Form(...), role: str = Form("SUPER_ADMIN"), security_question: str = Form(""), security_answer: str = Form(""), mobile: str = Form(""), email: str = Form(""), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).limit(1)) is not None:
        return JSONResponse({"error": "setup_already_completed"}, status_code=409)
    role = role.upper()
    if role != "SUPER_ADMIN":
        return JSONResponse({"error": "first_setup_must_create_super_admin"}, status_code=400)
    if not security_question.strip() or not security_answer.strip():
        return JSONResponse({"error": "super_admin_security_question_required"}, status_code=400)
    user = User(username=username.strip(), password_hash=hash_password(password), role=role, mobile=mobile.strip() or None, email=email.strip().lower() or None, security_question=security_question.strip(), security_answer_hash=hash_password(security_answer.strip()), is_active=True, is_approved=True)
    db.add(user)
    db.commit()
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
@app.post("/auth/super-admin/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), method: str = Form(...), portal: str = Form(""), db: Session = Depends(get_db)):
    super_admin_only = portal == "super_admin" or request.url.path == "/auth/super-admin/login"
    if super_admin_only and _super_admin_rate_limited(request, username):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Too many failed Super Admin login attempts. Please wait 15 minutes before trying again.", "super_admin_only": True}, status_code=429)
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not authenticate_password(user, password):
        if super_admin_only:
            _record_super_admin_failure(request, username)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password.", "super_admin_only": super_admin_only}, status_code=401)
    if super_admin_only and user.role != "SUPER_ADMIN":
        _record_super_admin_failure(request, username)
        return templates.TemplateResponse("login.html", {"request": request, "error": "This portal is restricted to Super Admin accounts.", "super_admin_only": True}, status_code=403)
    if super_admin_only:
        _clear_super_admin_failures(request, username)
    methods = allowed_methods(user.role)
    if method not in methods:
        return templates.TemplateResponse("login.html", {"request": request, "error": "This verification method is not allowed for your role.", "super_admin_only": super_admin_only}, status_code=403)
    email_verified = db.scalar(select(EmailVerification.id).where(EmailVerification.user_id == user.id)) is not None
    if method == "email_otp" and not user.email:
        return templates.TemplateResponse("login.html", {"request": request, "error": "No registered email is available for this account.", "super_admin_only": super_admin_only}, status_code=400)
    if method != "email_otp" and not (user.is_approved or email_verified):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Account access requires either email verification or administrator approval.", "super_admin_only": super_admin_only}, status_code=403)
    if method == "approval" and not user.is_approved:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Administrator approval has not been granted.", "super_admin_only": super_admin_only}, status_code=403)
    if method in {"mobile_otp", "email_otp"}:
        destination_value = user.mobile if method == "mobile_otp" else user.email
        if not destination_value:
            return templates.TemplateResponse("login.html", {"request": request, "error": f"No registered {('mobile' if method == 'mobile_otp' else 'email')} is available for this account.", "super_admin_only": super_admin_only}, status_code=400)
        try:
            otp, delivery = generate_and_send_otp("mobile" if method == "mobile_otp" else "email", destination_value)
        except RuntimeError as exc:
            _audit(db, user.id, "OTP_DELIVERY_FAILED", user, {"error": str(exc)})
            db.commit()
            return templates.TemplateResponse("login.html", {"request": request, "error": "OTP delivery is not configured. Contact the administrator.", "super_admin_only": super_admin_only}, status_code=503)
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
            db.add(EmailVerification(user_id=user.id, verified_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        else:
            existing.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["session_version"] = user.session_version
    _audit(db, user.id, "LOGIN_SUCCESS", user, {"method": method})
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    last_login = db.scalar(select(AuditEvent.created_at).where(AuditEvent.actor_user_id == user.id, AuditEvent.action == "LOGIN_SUCCESS").order_by(AuditEvent.created_at.desc()).limit(1))
    return templates.TemplateResponse("profile.html", {"request": request, "username": user.username, "role": user.role, "avatar": user.username[:1].upper(), "user": user, "last_login": last_login, "csrf_token": csrf_token(request)})


@app.post("/profile", dependencies=[Depends(require_csrf)])
def update_profile(request: Request, mobile: str = Form(""), email: str = Form(""), category: str = Form(""), team: str = Form(""), security_question: str = Form(""), security_answer: str = Form(""), db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    user.mobile = mobile.strip() or None
    user.email = email.strip().lower() or None
    user.category = category.strip() or None
    user.team = team.strip() or None
    if security_question.strip() and security_answer.strip():
        user.security_question = security_question.strip()
        user.security_answer_hash = hash_password(security_answer.strip())
    _audit(db, user.id, "PROFILE_UPDATED", user)
    db.commit()
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/password", dependencies=[Depends(require_csrf)])
def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    if not authenticate_password(user, current_password):
        return RedirectResponse("/profile?password_error=invalid_current", status_code=303)
    if len(new_password) < 8 or new_password != confirm_password:
        return RedirectResponse("/profile?password_error=invalid_new", status_code=303)
    user.password_hash = hash_password(new_password)
    user.session_version += 1
    request.session.clear()
    _audit(db, user.id, "PASSWORD_CHANGED", user)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="administrator_required")
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    managers = [u for u in users if u.is_active and u.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}]
    return templates.TemplateResponse("admin_users.html", {"request": request, "username": actor.username, "role": actor.role, "avatar": actor.username[:1].upper(), "users": users, "managers": managers, "roles": [r.value for r in Role], "access_values": [a.value for a in Access], "csrf_token": csrf_token(request)})


@app.post("/admin/users", dependencies=[Depends(require_csrf)])
def create_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...), mobile: str = Form(""), email: str = Form(""), category: str = Form(""), team: str = Form(""), reporting_manager_id: int | None = Form(None), permissions_json: str = Form("{}"), field_visibility_json: str = Form("{}"), is_approved: bool = Form(False), db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    role = role.upper()
    if not actor or not _can_manage_user(actor, target_role=role):
        raise HTTPException(status_code=403, detail="user_management_not_permitted")
    if not _valid_reporting_manager(actor, reporting_manager_id, None, db):
        raise HTTPException(status_code=400, detail="invalid_reporting_manager")
    username = username.strip()
    if not username or len(password) < 8 or db.scalar(select(User.id).where(User.username == username)) is not None:
        return RedirectResponse("/admin/users?error=invalid_or_duplicate_user", status_code=303)
    user = User(username=username, password_hash=hash_password(password), role=role, mobile=mobile.strip() or None, email=email.strip().lower() or None, category=category.strip() or None, team=team.strip() or None, reporting_manager_id=reporting_manager_id, permissions_json=json.dumps(_json_object(permissions_json)), field_visibility_json=json.dumps(_json_object(field_visibility_json)), is_active=True, is_approved=bool(is_approved))
    db.add(user)
    db.flush()
    _audit(db, actor.id, "USER_CREATED", user, {"role": role})
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/edit", dependencies=[Depends(require_csrf)])
def edit_user(user_id: int, request: Request, role: str = Form(...), mobile: str = Form(""), email: str = Form(""), category: str = Form(""), team: str = Form(""), reporting_manager_id: int | None = Form(None), permissions_json: str = Form("{}"), field_visibility_json: str = Form("{}"), db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    role = role.upper()
    if not actor or not target or not _can_manage_user(actor, target, role):
        raise HTTPException(status_code=403, detail="user_management_not_permitted")
    if not _valid_reporting_manager(actor, reporting_manager_id, target, db):
        raise HTTPException(status_code=400, detail="invalid_reporting_manager")
    if target.id == actor.id and role != "SUPER_ADMIN":
        raise HTTPException(status_code=400, detail="cannot_remove_own_super_admin_access")
    target.role = role
    target.mobile = mobile.strip() or None
    target.email = email.strip().lower() or None
    target.category = category.strip() or None
    target.team = team.strip() or None
    target.reporting_manager_id = reporting_manager_id if reporting_manager_id != target.id else None
    target.permissions_json = json.dumps(_json_object(permissions_json))
    target.field_visibility_json = json.dumps(_json_object(field_visibility_json))
    _audit(db, actor.id, "USER_UPDATED", target, {"role": role})
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/toggle", dependencies=[Depends(require_csrf)])
def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target or not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user_management_not_permitted")
    if target.id == actor.id and target.is_active:
        raise HTTPException(status_code=400, detail="cannot_disable_current_user")
    target.is_active = not target.is_active
    target.session_version += 1
    _audit(db, actor.id, "USER_ENABLED" if target.is_active else "USER_DISABLED", target)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/reset-sessions", dependencies=[Depends(require_csrf)])
def reset_user_sessions(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target or not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user_management_not_permitted")
    target.session_version += 1
    _audit(db, actor.id, "USER_SESSIONS_RESET", target)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/reset-password", dependencies=[Depends(require_csrf)])
def reset_user_password(user_id: int, request: Request, new_password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target or not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user_management_not_permitted")
    if len(new_password) < 8 or new_password != confirm_password:
        return RedirectResponse("/admin/users?error=invalid_password", status_code=303)
    target.password_hash = hash_password(new_password)
    target.session_version += 1
    _audit(db, actor.id, "USER_PASSWORD_RESET", target)
    db.commit()
    return _browser_redirect(request, "/admin/users", {"status": "password_reset", "user_id": target.id})


@app.get("/admin/users/pending")
def pending_users(request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="administrator_required")
    users = db.scalars(select(User).where(User.is_active.is_(True), User.is_approved.is_(False)).order_by(User.created_at)).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "email": u.email, "created_at": u.created_at.isoformat() if u.created_at else None} for u in users]


@app.post("/admin/users/{user_id}/approve", dependencies=[Depends(require_csrf)])
def approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if not _can_approve(actor, target):
        return JSONResponse({"error": "approval_not_permitted"}, status_code=403)
    target.is_approved = True
    _audit(db, actor.id, "USER_APPROVED", target, {"target_role": target.role})
    db.commit()
    return _browser_redirect(request, "/admin/users", {"status": "approved", "user_id": target.id})


@app.post("/admin/users/{user_id}/revoke-approval", dependencies=[Depends(require_csrf)])
def revoke_user_approval(user_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _current_user(request, db)
    target = db.get(User, user_id)
    if not actor or not target:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if not _can_approve(actor, target):
        return JSONResponse({"error": "approval_not_permitted"}, status_code=403)
    target.is_approved = False
    target.session_version += 1
    _audit(db, actor.id, "USER_APPROVAL_REVOKED", target, {"target_role": target.role})
    db.commit()
    return _browser_redirect(request, "/admin/users", {"status": "approval_revoked", "user_id": target.id})


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
        "show_user_management": user.role in {"SUPER_ADMIN", "ADMIN"},
    })


@app.get("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        _audit(db, user_id, "LOGOUT")
        db.commit()
    request.session.clear()
    response = RedirectResponse("/", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
