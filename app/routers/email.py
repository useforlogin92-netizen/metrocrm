"""Role-scoped property email sharing for assigned CRM leads."""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, Project, Unit, User
from app.services.email import send_email

router = APIRouter(prefix="/email", tags=["email"])
SEND_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER", "USER"}


def _user(request: Request, db: Session) -> User:
    from app.main import _current_user
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401, "authentication_required")
    if user.role not in SEND_ROLES:
        raise HTTPException(403, "email_not_permitted")
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
    if not customer or not customer.email:
        raise HTTPException(400, "customer_email_required")
    return lead, customer


@router.post("/property-share", dependencies=[Depends(require_csrf)])
def share_property_email(
    request: Request,
    lead_id: int = Form(...), project_id: int = Form(...), unit_id: int = Form(...),
    csrf_token_value: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf_token_value)
    user = _user(request, db)
    lead, customer = _lead_for_user(lead_id, user, db)
    project = db.get(Project, project_id)
    unit = db.get(Unit, unit_id)
    if not project or not unit or unit.project_id != project.id:
        raise HTTPException(404, "property_not_found")

    location = ", ".join(value for value in (project.locality, project.city, project.address) if value)
    subject = f"Property details: {project.name} — {unit.unit_number}"
    facts = [
        ("Project", project.name),
        ("Unit", unit.unit_number),
        ("Location", location),
        ("Configuration", unit.bhk),
        ("Property Type", unit.property_type),
        ("Carpet Area", f"{unit.carpet_area} sq. ft." if unit.carpet_area is not None else None),
        ("Price", f"₹{float(unit.price):,.0f}" if unit.price is not None else None),
        ("Rate per sq. ft.", f"₹{float(unit.price_per_sqft):,.0f}" if unit.price_per_sqft is not None else None),
        ("Parking", unit.parking),
        ("Possession", unit.possession or (project.possession_date.strftime("%b %Y") if project.possession_date else None)),
        ("RERA", unit.rera or project.rera),
    ]
    detail_lines = [f"{label}: {value}" for label, value in facts if value]
    body = (
        f"Dear {customer.name},\n\n"
        "As discussed, please find the property details below. Please contact your Metro Property consultant if you would like to arrange a site visit or discuss the next steps.\n\n"
        + "\n".join(detail_lines)
        + "\n\nRegards,\nMetro Property"
    )
    status = "FAILED"
    error = None
    try:
        result = send_email(customer.email, subject, body)
        status = result.get("status", "TEST")
    except (RuntimeError, ValueError) as exc:
        error = str(exc)
    recipient_hash = hashlib.sha256(customer.email.strip().lower().encode("utf-8")).hexdigest()[:16]
    db.add(AuditEvent(
        actor_user_id=user.id, action="PROPERTY_EMAIL_SHARE", entity_type="Lead", entity_id=str(lead.id),
        details=json.dumps({"status": status, "project_id": project.id, "unit_id": unit.id, "recipient_hash": recipient_hash, "error": error}),
    ))
    db.commit()
    if status == "FAILED":
        raise HTTPException(502, error or "email_delivery_failed")
    return RedirectResponse(f"/caller/lead/{lead.id}/call?email_status={status}", status_code=303)
