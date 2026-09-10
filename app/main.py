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
import app.whatsapp_models  # noqa: F401
import app.email_verification  # noqa: F401

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_backup_scheduler()
    try:
        yield
    finally:
        stop_backup_scheduler()