"""Admin-configurable external integrations and instant property-visit intake."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.integration_models import IntegrationConfig, PropertyVisitAlert
from app.models import AuditEvent, User
from app.csrf import require_csrf_header
from app.services.integrations import SUPPORTED_LEAD_PROVIDERS, ingest_lead, verify_webhook_signature

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
    _management(request, db)
    enabled = {row.provider: row.enabled for row in db.scalars(select(IntegrationConfig)).all()}
    return {"providers": [{"name": p, "enabled": bool(enabled.get(p, False))} for p in SUPPORTED_LEAD_PROVIDERS],
            "otp": {"mobile": settings.otp_mobile_provider, "email": settings.otp_email_provider},
            "property_visit_alerts": settings.property_visit_alerts_enabled}


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
    safe_settings = {k: v for k, v in body.items() if k in {"mode", "webhook_url", "page_id", "form_id", "notes"}}
    row.settings_json = json.dumps(safe_settings)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=user.id, action="INTEGRATION_CONFIG_UPDATED", entity_type="IntegrationConfig", entity_id=provider, details=json.dumps({"enabled": row.enabled, "mode": row.mode})))
    db.commit()
    return {"provider": provider, "enabled": row.enabled, "mode": row.mode}


@router.post("/lead/{provider}")
async def lead_webhook(provider: str, request: Request, x_metrocrm_signature: str | None = Header(default=None), db: Session = Depends(get_db)):
    provider = provider.lower().strip()
    config = db.scalar(select(IntegrationConfig).where(IntegrationConfig.provider == provider))
    if provider not in SUPPORTED_LEAD_PROVIDERS or config is None or not config.enabled:
        raise HTTPException(404, "integration_provider_not_enabled")
    raw = await request.body()
    if not settings.lead_integrations_enabled or not verify_webhook_signature(raw, x_metrocrm_signature):
        raise HTTPException(401, "invalid_integration_signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
        event = ingest_lead(db, provider, payload, raw)
        return {"status": event.status, "event_id": event.id, "lead_id": event.lead_id}
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/property-visit")
async def property_visit(request: Request, body: dict, db: Session = Depends(get_db)):
    """Called by customer-facing property/project pages immediately when a visit is recorded."""
    if not settings.property_visit_alerts_enabled:
        return {"status": "disabled"}
    project_id = body.get("project_id")
    unit_id = body.get("unit_id")
    if not project_id and not unit_id:
        raise HTTPException(400, "project_id_or_unit_id_required")
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256((settings.secret_key + client_ip).encode()).hexdigest()
    recent = db.scalar(select(PropertyVisitAlert).where(
        PropertyVisitAlert.project_id == project_id,
        PropertyVisitAlert.unit_id == unit_id,
        PropertyVisitAlert.visitor_ip_hash == ip_hash,
        PropertyVisitAlert.created_at >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=settings.property_visit_alert_cooldown_seconds),
    ))
    if recent:
        return {"status": "already_recorded", "alert_id": recent.id}
    alert = PropertyVisitAlert(project_id=project_id, unit_id=unit_id, lead_id=body.get("lead_id"), visitor_ip_hash=ip_hash,
                               user_agent=(request.headers.get("user-agent") or "")[:500], page_url=str(body.get("page_url") or "")[:1000])
    db.add(alert)
    db.add(AuditEvent(action="PROPERTY_CATALOG_VISIT", entity_type="PropertyVisitAlert", entity_id="pending", details=json.dumps({"project_id": project_id, "unit_id": unit_id})))
    db.commit(); db.refresh(alert)
    return {"status": "alerted", "alert_id": alert.id, "notify_roles": ["ADMIN", "SUPER_ADMIN"]}


@router.get("/property-visits", response_class=HTMLResponse)
def property_visit_alerts_page(request: Request, db: Session = Depends(get_db)):
    user = _management(request, db)
    if user.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(403, "admin_or_super_admin_required")
    rows = db.scalars(select(PropertyVisitAlert).order_by(PropertyVisitAlert.created_at.desc()).limit(100)).all()
    context = _shell_context(request, user)
    context["alerts"] = rows
    return templates.TemplateResponse("property_visit_alerts.html", context)


@router.get("/property-visits/alerts")
def property_visit_alerts(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if user.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(403, "admin_or_super_admin_required")
    rows = db.scalars(select(PropertyVisitAlert).order_by(PropertyVisitAlert.created_at.desc()).limit(100)).all()
    return [{"id": r.id, "project_id": r.project_id, "unit_id": r.unit_id, "lead_id": r.lead_id,
             "status": r.status, "created_at": r.created_at.isoformat(), "notified": r.notified} for r in rows]
