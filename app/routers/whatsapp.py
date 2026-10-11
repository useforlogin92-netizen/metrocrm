"""Controlled WhatsApp messaging from CRM records and property catalog shares."""
from __future__ import annotations
import json
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogShare
from app.routers.catalog_sharing import _token_hash as catalog_token_hash
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, Project, Unit, User
from app.routers.caller_assistant import _lead_in_scope, _unit_is_unavailable
from app.services.catalog_sharing import build_share_payload
from app.services.whatsapp import build_property_message, destination_hash, send_text
from app.routers.branding_settings import BrandingSettings, render_message_template
from app.whatsapp_models import WhatsAppMessage

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
templates = Jinja2Templates(directory="app/templates")
SEND_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER", "USER"}


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
    if not _lead_in_scope(user, lead, db):
        raise HTTPException(403, "lead_outside_scope")
    if not lead.customer_id:
        raise HTTPException(400, "lead_has_no_customer")
    customer = db.get(Customer, lead.customer_id)
    if not customer or not customer.mobile:
        raise HTTPException(400, "customer_mobile_required")
    return lead, customer


def _scope_user_ids(user: User, db: Session) -> set[int]:
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        return set(db.scalars(select(User.id)).all())
    ids = {user.id}
    if user.role in {"MANAGER", "TL"}:
        frontier = {user.id}
        while frontier:
            children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
            frontier = {int(uid) for uid in children if int(uid) not in ids}
            ids.update(frontier)
    return ids


def _shell(request: Request, user: User) -> dict:
    return {
        "request": request, "username": user.username, "role": user.role,
        "avatar": user.username[:1].upper(), "csrf_token": csrf_token(request),
        "show_integrations": user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"},
        "show_alerts": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_approvals": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_user_management": user.role in {"SUPER_ADMIN", "ADMIN"},
        "show_whatsapp": True,
    }


@router.get("", response_class=HTMLResponse)
def whatsapp_page(request: Request, db: Session = Depends(get_db)):
    from app.config import settings
    user = _user(request, db)
    context = _shell(request, user)
    scope_ids = _scope_user_ids(user, db)
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        lead_query = select(Lead).order_by(Lead.created_at.desc()).limit(500)
    else:
        lead_query = select(Lead).where(Lead.assigned_user_id.in_(scope_ids)).order_by(Lead.created_at.desc()).limit(500)
    leads = db.scalars(lead_query).all()
    context["leads"] = leads
    context["customers"] = {
        customer.id: customer
        for customer in db.scalars(
            select(Customer).where(Customer.id.in_({lead.customer_id for lead in leads if lead.customer_id is not None}))
        ).all()
    } if any(lead.customer_id is not None for lead in leads) else {}
    available_properties = []
    for unit, project in db.execute(
        select(Unit, Project).join(Project, Unit.project_id == Project.id).order_by(Project.name, Unit.unit_number).limit(2000)
    ).all():
        if not _unit_is_unavailable(unit, project):
            available_properties.append({
                "id": unit.id, "project_id": project.id, "unit_number": unit.unit_number,
                "project_name": project.name, "bhk": unit.bhk, "property_type": unit.property_type,
                "locality": project.locality, "city": project.city, "price": unit.price,
            })
    context["available_properties"] = available_properties
    context.update({"whatsapp_enabled": bool(settings.whatsapp_enabled), "whatsapp_mode": settings.whatsapp_mode})
    return templates.TemplateResponse(request, "whatsapp.html", context)


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
        status = "FAILED"; provider_id = None; error = str(exc); result = {"status": status, "error": error}
    log = WhatsAppMessage(actor_user_id=user.id, lead_id=lead.id, customer_id=customer.id,
                          destination_hash=destination_hash(customer.mobile), message_type="text",
                          body_preview=body[:500], status=status, provider_message_id=provider_id, error=error)
    db.add(log)
    db.add(AuditEvent(actor_user_id=user.id, action="WHATSAPP_MESSAGE_SENT", entity_type="Lead", entity_id=str(lead.id),
                      details=json.dumps({"status": status, "message_type": "text"})))
    db.commit()
    if status == "FAILED":
        raise HTTPException(502, error or "whatsapp_delivery_failed")
    return {"status": status, "message_id": log.id, "provider_message_id": provider_id, "result": result}


@router.post("/property-share", dependencies=[Depends(require_csrf)])
def share_property_whatsapp(request: Request, lead_id: int = Form(...), unit_id: int = Form(...), project_id: int | None = Form(None), db: Session = Depends(get_db)):
    user = _user(request, db)
    lead, customer = _lead_for_user(lead_id, user, db)
    unit = db.get(Unit, unit_id)
    project = db.get(Project, project_id) if project_id else (db.get(Project, unit.project_id) if unit else None)
    if not project or not unit or unit.project_id != project.id:
        raise HTTPException(404, "property_not_found")
    if _unit_is_unavailable(unit, project):
        raise HTTPException(409, "property_unavailable")
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
    db.add(share); db.flush()
    from app.config import settings
    share_url = f"{settings.whatsapp_public_base_url.rstrip('/')}/catalog/view/{token}" if settings.whatsapp_public_base_url else f"/catalog/view/{token}"
    body = build_property_message(property_data, share_url)
    branding = db.get(BrandingSettings, 1)
    if branding and branding.whatsapp_template.strip():
        greeting = render_message_template(branding.whatsapp_template, {
            "Company_Name": branding.company_name,
            "Project_Name": project.name,
            "Agent_Name": user.username,
            "Customer_Name": customer.name,
        }).strip()
        if greeting:
            body = f"{greeting}\\n\\n{body}"
    try:
        result = send_text(customer.mobile, body)
        status = result.get("status", "TEST"); provider_id = result.get("provider_message_id"); error = None
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
