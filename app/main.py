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

authenticated_session_state = {"user_id", "session_version", "login_portal"}

@app.middleware("http")
async def enforce_idle_session(request: Request, call_next):
    user_id = request.session.get("user_id")
    if user_id:
        now = time.time()
        last_activity = request.session.get("last_activity")
        try:
            last_activity = float(last_activity) if last_activity is not None else 0.0
        except (TypeError, ValueError):
            last_activity = 0.0
        if not last_activity or now - last_activity >= settings.session_max_age:
            request.session.clear()
            response = RedirectResponse("/auth/logout", status_code=303)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        request.session["last_activity"] = now
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

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
