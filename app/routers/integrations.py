"""Admin-configurable external integrations and instant property-visit intake."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.integration_models import IntegrationConfig, PropertyVisitAlert
from app.models import AuditEvent, User
from app.csrf import csrf_token, require_csrf_header
from app.services.integrations import SUPPORTED_LEAD_PROVIDERS, ingest_lead, verify_webhook_signature
from app.services.integration_secrets import encrypt_credentials

router = APIRouter(prefix="/integrations", tags=["integrations"])
MANAGEMENT_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}
templates = Jinja2Templates(directory="app/templates")


def _user(request: Request, db: Session) -> User:
    from app.main import _current_user
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401, "authentication_required")
    return user


def _management(request: Request, db: Session) -> User:
    user = _user(request, db)
    if user.role not in MANAGEMENT_ROLES:
        raise HTTPException(403, "management_role_required")
    return user


def _shell_context(request: Request, user: User) -> dict:
    return {
        "request": request,
        "username": user.username,
        "role": user.role,
        "avatar": user.username[:1].upper(),
        "show_integrations": user.role in MANAGEMENT_ROLES,
        "show_alerts": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_approvals": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_user_management": user.role in {"SUPER_ADMIN", "ADMIN"},
    }


@router.get("/providers")
def providers(request: Request, db: Session = Depends(get_db)):
    user = _management(request, db)
    rows = db.scalars(select(IntegrationConfig)).all()
    configs = {row.provider: row for row in rows}
    wants_json = "application/json" in request.headers.get("accept", "") and "text/html" not in request.headers.get("accept", "")
    payload = {"providers": [{"name": p, "enabled": bool(configs[p].enabled) if p in configs else False, "mode": configs[p].mode if p in configs else "webhook", "configured": p in configs, "has_credentials": bool(configs[p].credentials_encrypted) if p in configs else False} for p in SUPPORTED_LEAD_PROVIDERS], "otp": {"mobile": settings.otp_mobile_provider, "email": settings.otp_email_provider}, "property_visit_alerts": settings.property_visit_alerts_enabled}
    if wants_json:
        return payload
    return templates.TemplateResponse("integrations_providers.html", {**_shell_context(request, user), "providers": payload["providers"], "otp": payload["otp"], "property_visit_alerts": payload["property_visit_alerts"], "csrf_token": csrf_token(request)})


@router.post("/providers/{provider}", dependencies=[Depends(require_csrf_header)])
def configure_provider(provider: str, body: dict, request: Request, db: Session = Depends(get_db)):
    user = _management(request, db)
    provider = provider.lower().strip()
    if provider not in SUPPORTED_LEAD_PROVIDERS:
        raise HTTPException(404, "unsupported_provider")
    row = db.scalar(select(IntegrationConfig).where(IntegrationConfig.provider == provider))
    if row is None:
        row = IntegrationConfig(provider=provider)
        db.add(row)
    row.enabled = bool(body.get("enabled", False))
    row.mode = str(body.get("mode", "webhook"))[:30]
    safe_settings = {k: v for k, v in body.items() if k in {"mode", "webhook_url", "page_id", "form_id", "notes", "auto_create_lead", "duplicate_handling", "assigned_user_id", "lead_source", "integration_name", "api_permission"}}
    row.settings_json = json.dumps(safe_settings)
    credentials = {k: str(body.get(k)).strip() for k in ("api_key", "api_secret", "access_token") if body.get(k)}
    if credentials:
        row.credentials_encrypted = encrypt_credentials(credentials)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=user.id, action="INTEGRATION_CONFIG_UPDATED", entity_type="IntegrationConfig", entity_id=provider, details=json.dumps({"enabled": row.enabled, "mode": row.mode})))
    db.commit()
    return {"provider": provider, "enabled": row.enabled, "mode": row.mode}


@router.post("/providers/{provider}/run", dependencies=[Depends(require_csrf_header)])
def test_provider(provider: str, request: Request, db: Session = Depends(get_db)):
    """Check integration configuration without sending or creating external data."""
    user = _management(request, db)
    provider = provider.lower().strip()
    if provider not in SUPPORTED_LEAD_PROVIDERS:
        raise HTTPException(404, "unsupported_provider")
    row = db.scalar(select(IntegrationConfig).where(IntegrationConfig.provider == provider))
    if row is None:
        return JSONResponse({"status": "PENDING", "provider": provider, "message": "Integration is not configured yet."}, status_code=409)
    try:
        cfg = json.loads(row.settings_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        cfg = {}
    checks = {
        "mode": bool(row.mode),
        "credentials": bool(row.credentials_encrypted) if row.mode == "api" else True,
        "webhook_url": bool(cfg.get("webhook_url")) if row.mode == "webhook" else True,
        "global_lead_integrations": bool(settings.lead_integrations_enabled),
    }
    status = "READY" if row.enabled and all(checks.values()) else "PENDING"
    db.add(AuditEvent(actor_user_id=user.id, action="INTEGRATION_TEST_CONNECTION", entity_type="IntegrationConfig", entity_id=provider, details=json.dumps({"checks": checks, "status": status})))
    db.commit()
    return {"status": status, "provider": provider, "checks": checks, "message": "Configuration check completed. No external lead was created."}


@router.post("/providers/{provider}/sync", dependencies=[Depends(require_csrf_header)])
def sync_provider(provider: str, request: Request, db: Session = Depends(get_db)):
    """Run a real provider sync only when a provider adapter is available."""
    user = _management(request, db)
    provider = provider.lower().strip()
    if provider not in SUPPORTED_LEAD_PROVIDERS:
        raise HTTPException(404, "unsupported_provider")
    row = db.scalar(select(IntegrationConfig).where(IntegrationConfig.provider == provider))
    if row is None or not row.enabled:
        return JSONResponse({"status": "PENDING", "provider": provider, "message": "Connect and enable this integration first."}, status_code=409)
    db.add(AuditEvent(actor_user_id=user.id, action="INTEGRATION_SYNC_REQUESTED", entity_type="IntegrationConfig", entity_id=provider, details=json.dumps({"status": "ADAPTER_PENDING"})))
    db.commit()
    return JSONResponse({"status": "ADAPTER_PENDING", "provider": provider, "message": "Connection is saved, but the provider-specific API sync adapter is not configured yet. No external data was changed."}, status_code=409)


@router.get("/property-visits", response_class=HTMLResponse)
def property_visits(request: Request, db: Session = Depends(get_db)):
    """Show recent property visit alerts to authenticated management users."""
    user = _management(request, db)
    rows = db.scalars(
        select(PropertyVisitAlert)
        .order_by(PropertyVisitAlert.created_at.desc())
        .limit(200)
    ).all()
    return templates.TemplateResponse(
        "integration_property_visits.html",
        {
            **_shell_context(request, user),
            "rows": rows,
            "csrf_token": csrf_token(request),
        },
    )


@router.get("/logs", response_class=HTMLResponse)
def integration_logs(request: Request, db: Session = Depends(get_db)):
    user = _management(request, db)
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "IntegrationConfig")
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    ).all()
    return templates.TemplateResponse("integration_logs.html", {**_shell_context(request, user), "rows": rows})


