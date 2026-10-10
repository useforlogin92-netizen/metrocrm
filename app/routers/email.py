"""Role-scoped property email sharing for assigned CRM leads."""
from __future__ import annotations

import hashlib
import json
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, Project, Unit, User
from app.routers.caller_assistant import _lead_in_scope, _unit_is_unavailable
from app.services.email import send_email

router = APIRouter(prefix="/email", tags=["email"])


def _visible_leads(user: User, db: Session) -> list[Lead]:
    """Return only leads the current employee is permitted to work on."""
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        statement = select(Lead).order_by(Lead.created_at.desc()).limit(500)
    else:
        scope_ids = {user.id}
        if user.role in {"MANAGER", "TL"}:
            frontier = {user.id}
            while frontier:
                children = db.scalars(
                    select(User.id).where(User.reporting_manager_id.in_(frontier))
                ).all()
                frontier = {int(uid) for uid in children if int(uid) not in scope_ids}
                scope_ids.update(frontier)
        statement = (
            select(Lead)
            .where(Lead.assigned_user_id.in_(scope_ids))
            .order_by(Lead.created_at.desc())
            .limit(500)
        )
    return list(db.scalars(statement).all())


@router.get("", response_class=HTMLResponse)
def email_workspace(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    leads = _visible_leads(user, db)
    customer_ids = {lead.customer_id for lead in leads if lead.customer_id is not None}
    customers = {
        customer.id: customer
        for customer in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()
    } if customer_ids else {}
    rows = []
    for lead in leads:
        customer = customers.get(lead.customer_id)
        name = escape(customer.name if customer else "Unlinked customer")
        email = escape(customer.email if customer and customer.email else "Email not added")
        if user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}:
            action = f'<a href="/caller/lead/{lead.id}/call">Open lead and share property</a>'
        else:
            action = "Not available for this role"
        rows.append(
            f"<tr><td>#{lead.id}</td><td>{name}</td><td>{email}</td>"
            f"<td>{escape(lead.source or 'Unknown')}</td><td>{escape(lead.status or 'NEW')}</td>"
            f"<td>{action}</td></tr>"
        )
    body = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>MetroCRM | Email Property Details</title>"
        "<style>body{font:14px Arial,sans-serif;background:#f4f7fb;color:#152238;margin:0;padding:24px}"
        "main{max-width:1200px;margin:auto}.card{background:#fff;border:1px solid #e0e7f0;border-radius:14px;padding:20px}"
        "table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #e8edf4}"
        "th{background:#f8fafc}a{color:#1d4ed8;font-weight:700}@media(max-width:750px){main{overflow:auto}table{min-width:800px}}</style>"
        "</head><body><main><div class='card'><h1>Email Property Details</h1>"
        "<p>Choose a lead to review matching properties and email the selected property details to its customer. "
        "Only leads within your permitted scope are listed.</p><p><a href='/dashboard'>Dashboard</a> · "
        "<a href='/caller/leads'>Lead Management</a></p><table><thead><tr><th>Lead</th><th>Customer</th>"
        "<th>Email</th><th>Source</th><th>Status</th><th>Action</th></tr></thead><tbody>"
        + ("".join(rows) or "<tr><td colspan='6'>No leads are available in your permitted scope.</td></tr>")
        + "</tbody></table></div></main></body></html>"
    )
    return HTMLResponse(body)
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
    if not _lead_in_scope(user, lead, db):
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
    if _unit_is_unavailable(unit, project):
        raise HTTPException(409, "property_unavailable")

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
