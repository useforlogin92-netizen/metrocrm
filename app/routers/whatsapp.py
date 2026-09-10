"""Controlled WhatsApp messaging from CRM records and property catalog shares."""
from __future__ import annotations
import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogShare
from app.catalog_sharing import _token_hash as catalog_token_hash
from app.csrf import require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, Project, Unit, User
from app.services.catalog_sharing import build_share_payload
from app.services.whatsapp import build_property_message, destination_hash, send_text
from app.whatsapp_models import WhatsAppMessage

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
templates = Jinja2Templates(directory="app/templates")
SEND_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "TELECALLER", "USER"}


def _user(request: Request, db: Session) -> User:
    from app.main import _current_user
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401, "authentication_required")
    if user.role not in SEND_ROLES:
        raise HTTPException(403, "whatsapp_not_permitted")
    return user


def _lead_for_user(lead_id: int, user: User, db: Session) -> tuple[Lead, Customer]:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "lead_not_found")
    if user.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER"} and lead.assigned_user_id != user.id:
        raise HTTPException(403, "lead_outside_scope")
    if not lead.customer_id:
        raise HTTPException(400, "lead_has_no_customer")
    customer = db.get(Customer, lead.customer_id)
    if not customer or not customer.mobile:
        raise HTTPException(400, "customer_mobile_required")
    return lead, customer


def _shell(request: Request, user: User) -> dict:
    return {
        "request": request, "username": user.username, "role": user.role,
        "avatar": user.username[:1].upper(),
        "show_integrations": user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"},
        "show_alerts": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_approvals": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_user_management": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_whatsapp": True,
    }


@router.get("", response_class=HTMLResponse)
def whatsapp_page(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    return templates.TemplateResponse("whatsapp.html", _shell(request, user) | {
        "whatsapp_enabled": bool(__import__("app.config", fromlist=["settings"]).settings.whatsapp_enabled),
        "whatsapp_mode": __import__("app.config", fromlist=["settings"]).settings.whatsapp_mode,
    })


@router.post("/send", dependencies=[Depends(require_csrf)])
def send_whatsapp(request: Request, lead_id: int = Form(...), message: str = Form(...), db: Session = Depends(get_db)):
    user = _user(request, db)
    lead, customer = _lead_for_user(lead_id, user, db)
    body = message.strip()
    if not body:
        raise HTTPException(400, "message_required")
    try:
        result = send_text(customer.mobile, body)
        status = result.get("status", "TEST")
        provider_id = result.get("provider_message_id")
        error = None
    except RuntimeError as exc:
        status = "FAILED"
        provider_id = None
        error = str(exc)
        result = {"status": status, "error": error}
    log = WhatsAppMessage(actor_user_id=user.id, lead_id=lead.id, customer_id=customer.id,
                          destination_hash=destination_hash(customer.mobile), message_type="text",
                          body_preview=body[:500], status=status, provider_message_id=provider_id,
                          error=error)
    db.add(log)
    db.add(AuditEvent(actor_user_id=user.id, action="WHATSAPP_MESSAGE_SENT", entity_type="Lead", entity_id=str(lead.id),
                      details=json.dumps({"status": status, "message_type": "text"})))
    db.commit()
    if status == "FAILED":
        raise HTTPException(502, error or "whatsapp_delivery_failed")
    return {"status": status, "message_id": log.id, "provider_message_id": provider_id, "result": result}


@router.post("/property-share", dependencies=[Depends(require_csrf)])
def share_property_whatsapp(
    request: Request,
    lead_id: int = Form(...),
    project_id: int = Form(...),
    unit_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    lead, customer = _lead_for_user(lead_id, user, db)
    project = db.get(Project, project_id)
    unit = db.get(Unit, unit_id)
    if not project or not unit or unit.project_id != project.id:
        raise HTTPException(404, "property_not_found")
    property_data = {
        "project_name": project.name, "unit_number": unit.unit_number,
        "property_type": unit.property_type, "bhk": unit.bhk,
        "carpet_area": str(unit.carpet_area) if unit.carpet_area is not None else None,
        "price": str(unit.price) if unit.price is not None else None,
        "location": ", ".join(x for x in (project.locality, project.city) if x),
        "possession": unit.possession or (project.possession_date.isoformat() if project.possession_date else None),
        "rera": unit.rera or project.rera,
    }
    payload = build_share_payload(property_data, selected_fields=frozenset(property_data), selected_media_ids=frozenset(), media=[], contacts={}, contact_selections=())
    token = secrets.token_urlsafe(32)
    share = CatalogShare(token_hash=catalog_token_hash(token), project_id=project.id, unit_id=unit.id,
                         payload_json=json.dumps(payload, default=str), created_by_id=user.id)
    db.add(share)
    db.flush()
    from app.config import settings
    share_url = f"{settings.whatsapp_public_base_url.rstrip('/')}/catalog/view/{token}" if settings.whatsapp_public_base_url else f"/catalog/view/{token}"
    body = build_property_message(property_data, share_url)
    try:
        result = send_text(customer.mobile, body)
        status = result.get("status", "TEST")
        provider_id = result.get("provider_message_id")
        error = None
    except RuntimeError as exc:
        status = "FAILED"; provider_id = None; error = str(exc); result = {"status": status, "error": error}
    log = WhatsAppMessage(actor_user_id=user.id, lead_id=lead.id, customer_id=customer.id,
                          destination_hash=destination_hash(customer.mobile), message_type="property",
                          body_preview=body[:500], property_context_json=json.dumps({"project_id": project.id, "unit_id": unit.id, "share_id": share.id}),
                          status=status, provider_message_id=provider_id, error=error)
    db.add(log)
    db.add(AuditEvent(actor_user_id=user.id, action="WHATSAPP_PROPERTY_SHARED", entity_type="Unit", entity_id=str(unit.id),
                      details=json.dumps({"lead_id": lead.id, "project_id": project.id, "status": status, "share_id": share.id})))
    db.commit()
    if status == "FAILED":
        raise HTTPException(502, error or "whatsapp_delivery_failed")
    return {"status": status, "message_id": log.id, "provider_message_id": provider_id, "share_url": share_url, "result": result}
