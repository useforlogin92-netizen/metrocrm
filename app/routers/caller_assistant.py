from __future__ import annotations

import json
from datetime import datetime
from html import escape
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token
from app.database import get_db
from app.models import Customer, CustomerRequirement, Lead, Project, Tower, Unit, User
from app.services.caller_search import filter_and_rank_properties

router = APIRouter(prefix="/caller", tags=["caller-assistant"])


def _current_user(request: Request, db: Session) -> User | None:
    from app.main import _current_user as resolve_user
    return resolve_user(request, db)


def _allowed(user: User) -> bool:
    return user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}


def _locations(raw: str | None) -> list[dict[str, str]]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        value = []
    if not isinstance(value, list):
        value = []
    result: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("location") or "").strip()
            side = str(item.get("side") or "Both").strip()
            priority = str(item.get("priority") or "Primary").strip()
            if name:
                result.append({"name": name, "side": side, "priority": priority})
        elif str(item).strip():
            result.append({"name": str(item).strip(), "side": "Both", "priority": "Primary"})
    return result


def _lead_locations(lead: Lead, requirement: CustomerRequirement | None) -> list[dict[str, str]]:
    locations = _locations(requirement.locations_json if requirement else None)
    if locations:
        return locations
    raw = (lead.preferred_location or "").strip()
    if not raw:
        return []
    return [{"name": item.strip(), "side": "Both", "priority": "Primary"} for item in raw.split(",") if item.strip()]


def _money(value: Any) -> str:
    if value is None:
        return "not specified"
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _property_rows(db: Session, customer: dict[str, Any]) -> list[dict[str, Any]]:
    stmt = select(Unit, Project, Tower).join(Project, Unit.project_id == Project.id).outerjoin(Tower, Unit.tower_id == Tower.id)
    properties: list[dict[str, Any]] = []
    for unit, project, tower in db.execute(stmt).all():
        location = " ".join(filter(None, [project.locality, project.sector, project.address]))
        properties.append({
            "id": unit.id, "title": f"{project.name} - {unit.unit_number}", "project": project.name,
            "developer": None, "tower": tower.name if tower else None, "location": location,
            "locality": project.locality, "city": project.city, "district": project.district, "state": project.state,
            "pincode": project.pincode, "bhk": unit.bhk, "property_type": unit.property_type,
            "carpet_area": float(unit.carpet_area) if unit.carpet_area is not None else None,
            "price": float(unit.price) if unit.price is not None else None,
            "price_per_sqft": float(unit.price_per_sqft) if unit.price_per_sqft is not None else None,
            "parking": unit.parking, "facing": unit.facing, "furnishing": unit.furnishing,
            "possession": unit.possession or (project.possession_date.strftime("%b %Y") if project.possession_date else None),
            "possession_date": project.possession_date, "rera_possession_date": project.possession_date,
            "rera": unit.rera or project.rera,
            "construction_status": project.construction_status or unit.status or unit.availability,
            "description": unit.description or project.description,
        })
    results = filter_and_rank_properties(customer, properties)
    by_id = {int(p["id"]): p for p in properties}
    return [{**by_id[int(r.property_id)], "score": round(r.score), "reasons": r.reasons, "location_category": r.location_category} for r in results[:50]]


def _opening_speech(user: User, lead: Lead, customer: Customer | None, locations: list[dict[str, str]]) -> str:
    name = (customer.name if customer else None) or "Sir/Ma'am"
    source = (lead.source or "your enquiry").strip()
    location_text = ", ".join(item["name"] for item in locations) or (lead.preferred_location or "your preferred location")
    bhk = lead.bhk or "the required configuration"
    return (f"Namaste {name} ji, main {user.username} bol raha/rahi hoon. "
            f"Aapne {source} par {location_text} mein {bhk} property ke liye enquiry ki thi. "
            "Aapki requirement ke according main aapko suitable property options batana chahta/chahti hoon.")


def _property_speech(property_: dict[str, Any], customer: Customer | None) -> str:
    customer_name = (customer.name if customer else "Sir/Ma'am")
    parts = [
        f"{customer_name} ji, aapki requirement ke according ek option hai {property_.get('project') or 'is project'}",
        f"jo {property_.get('location') or 'preferred location'} mein located hai.",
    ]
    details = []
    for label, value in (("configuration", property_.get("bhk")), ("carpet area", property_.get("carpet_area")),
                         ("rate", property_.get("price_per_sqft")), ("all-inclusive price", property_.get("price")),
                         ("parking", property_.get("parking")), ("negotiable", property_.get("negotiable")),
                         ("possession", property_.get("possession")), ("RERA", property_.get("rera"))):
        if value not in (None, ""):
            if label == "carpet area": details.append(f"{value:g} square feet carpet area")
            elif label == "rate": details.append(f"{_money(value)} per square feet")
            elif label == "all-inclusive price": details.append(_money(value) + " all inclusive")
            elif label == "negotiable": details.append("price is negotiable" if str(value).casefold() in {"yes", "true", "1"} else "price is not negotiable")
            else: details.append(f"{label} {value}")
    if details:
        parts.append("Ismein " + ", ".join(details) + ".")
    if property_.get("description"):
        parts.append(f"Project ki main highlight hai: {str(property_['description']).strip()}")
    parts.append("Agar aapko ye option suitable lage, to main aapke liye next step ya site visit arrange kar sakta/sakti hoon.")
    return " ".join(parts)


@router.get("/lead/{lead_id}/call", response_class=HTMLResponse)
def lead_call_assistant(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user or not _allowed(user):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead:
        return HTMLResponse("Lead not found", status_code=404)
    customer = db.get(Customer, lead.customer_id) if lead.customer_id else None
    requirement = db.scalar(select(CustomerRequirement).where(CustomerRequirement.customer_id == lead.customer_id, CustomerRequirement.is_active.is_(True)).order_by(CustomerRequirement.updated_at.desc()).limit(1)) if lead.customer_id else None
    locations = _lead_locations(lead, requirement)
    customer_data = {
        "city": "Mumbai",
        "preferred_locations": [x["name"] for x in locations],
        "bhk": (requirement.bhk if requirement else None) or lead.bhk,
        "property_type": (requirement.property_type if requirement else None) or lead.property_type,
        "budget_min": (requirement.budget_min if requirement else None) or lead.budget_min,
        "budget_max": (requirement.budget_max if requirement else None) or lead.budget_max,
        "carpet_area_min": requirement.carpet_area_min if requirement else None,
        "carpet_area_max": requirement.carpet_area_max if requirement else None,
        "construction_statuses": [],
    }
    properties = _property_rows(db, customer_data)
    for item in properties:
        if not item.get("negotiable") and item.get("description"):
            try:
                meta = json.loads(item["description"]) if str(item["description"]).lstrip().startswith("{") else {}
                item["negotiable"] = meta.get("negotiable")
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    return request.app.state.templates.TemplateResponse("caller_lead_assistant.html", {
        "request": request, "user": user, "lead": lead, "customer": customer,
        "requirement": requirement, "locations": locations, "properties": properties,
        "opening_speech": _opening_speech(user, lead, customer, locations),
        "property_speech": {str(p["id"]): _property_speech(p, customer) for p in properties},
        "csrf_token": csrf_token(request), "now": datetime.now().strftime("%d %b %Y %H:%M"),
    })
