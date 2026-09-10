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
from app.routers.data_tools import router as data_tools_router
from app.routers.crm_plus import router as crm_plus_router
from app.routers.realestate_finance import router as realestate_finance_router
from app.routers.advanced_reports import router as advanced_reports_router
from app.routers.lead_import import router as lead_import_router
from app.routers.property_social import router as property_social_router
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

@app.middleware("http")
async def enforce_idle_session(request: Request, call_next):
    session = request.session
    user_id = session.get("user_id")
    if user_id:
        now = time.time()
        last_activity = session.get("last_activity")
        try:
            last_activity = float(last_activity) if last_activity is not None else 0.0
        except (TypeError, ValueError):
            last_activity = 0.0
        if not last_activity:
            session.clear()
            response = RedirectResponse("/", status_code=303)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        if now - last_activity >= settings.session_max_age:
            session.clear()
            response = RedirectResponse("/", status_code=303)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        session["last_activity"] = now
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=settings.session_max_age, https_only=settings.environment == "production", same_site="lax")
templates = Jinja2Templates(directory="app/templates")
app.include_router(catalog_sharing_router)
app.include_router(caller_search_router)
app.include_router(backups_router)
app.include_router(integrations_router)
app.include_router(data_tools_router)
app.include_router(crm_plus_router)
app.include_router(realestate_finance_router)
app.include_router(advanced_reports_router)
app.include_router(lead_import_router)
app.include_router(property_social_router)

_super_admin_failures: dict[str, list[float]] = {}
_SUPER_ADMIN_MAX_FAILURES = 5
_SUPER_ADMIN_WINDOW_SECONDS = 15 * 60


def _super_admin_rate_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}:"


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
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None, "super_admin_only": False})


@app.get("/super-admin/login", response_class=HTMLResponse)
def super_admin_login_page(request: Request):
    if request.session.get("user_id") and request.session.get("login_portal") == "super_admin":
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None, "super_admin_only": True})


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
