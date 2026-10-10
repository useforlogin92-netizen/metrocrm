from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, CustomerRequirement, Developer, FollowUp, Lead, Project, Tower, Unit, User
from app.services.caller_search import filter_and_rank_properties

router = APIRouter(prefix="/caller", tags=["caller-assistant"])
templates = Jinja2Templates(directory="app/templates")


def _current_user(request: Request, db: Session) -> User | None:
    from app.main import _current_user as resolve_user
    return resolve_user(request, db)


def _allowed(user: User) -> bool:
    return user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}


def _lead_in_scope(user: User, lead: Lead, db: Session) -> bool:
    """Enforce the same ownership/reporting-tree scope used by staff reports."""
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        return True
    if lead.assigned_user_id == user.id:
        return True
    if user.role not in {"MANAGER", "TL"}:
        return False
    ids = {user.id}
    changed = True
    while changed:
        changed = False
        children = db.scalars(select(User).where(User.reporting_manager_id.in_(ids))).all()
        for child in children:
            if child.id not in ids:
                ids.add(child.id)
                changed = True
    return lead.assigned_user_id in ids


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


def _unit_is_unavailable(unit: Unit, project: Project) -> bool:
    unavailable_states = {
        "sold", "sold_out", "booked", "reserved", "unavailable",
        "not_available", "inactive", "archived", "deleted", "blocked",
        "on_hold", "hold",
    }
    unit_states = {
        str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
        for value in (unit.status, unit.availability)
    }
    project_state = str(project.construction_status or "").strip().casefold().replace("-", "_").replace(" ", "_")
    return bool(unit_states & unavailable_states) or project_state in {
        "sold", "sold_out", "unavailable", "inactive", "archived", "deleted",
    }


def _property_rows(db: Session, customer: dict[str, Any]) -> list[dict[str, Any]]:
    stmt = select(Unit, Project, Tower, Developer).join(Project, Unit.project_id == Project.id).outerjoin(Tower, Unit.tower_id == Tower.id).outerjoin(Developer, Project.developer_id == Developer.id)
    properties: list[dict[str, Any]] = []
    for unit, project, tower, developer in db.execute(stmt).all():
        if _unit_is_unavailable(unit, project):
            continue
        location = " ".join(filter(None, [project.locality, project.sector, project.address]))
        properties.append({
            "id": unit.id, "project_id": project.id, "title": f"{project.name} - {unit.unit_number}", "project": project.name,
            "developer": developer.name if developer else None, "tower": tower.name if tower else None, "location": location,
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


def _speech_details(property_: dict[str, Any]) -> list[tuple[str, Any]]:
    details: list[tuple[str, Any]] = []
    for label, value in (("developer", property_.get("developer")), ("property type", property_.get("property_type")),
                         ("configuration", property_.get("bhk")), ("carpet area", property_.get("carpet_area")),
                         ("rate", property_.get("price_per_sqft")), ("all-inclusive price", property_.get("price")),
                         ("parking", property_.get("parking")), ("furnishing", property_.get("furnishing")),
                         ("negotiable", property_.get("negotiable")), ("possession", property_.get("possession")),
                         ("RERA", property_.get("rera"))):
        if value in (None, ""):
            continue
        if label == "carpet area":
            details.append((label, f"{value:g} square feet carpet area"))
        elif label == "rate":
            details.append((label, f"{_money(value)} per square feet"))
        elif label == "all-inclusive price":
            details.append((label, _money(value) + " all inclusive"))
        elif label == "negotiable":
            details.append((label, "price is negotiable" if str(value).casefold() in {"yes", "true", "1"} else "price is not negotiable"))
        else:
            details.append((label, f"{label} {value}"))
    return details


def _opening_speeches(user: User, lead: Lead, customer: Customer | None, locations: list[dict[str, str]]) -> dict[str, str]:
    name = (customer.name if customer else None) or "Sir/Ma'am"
    source = (lead.source or "your enquiry").strip()
    location_text = ", ".join(item["name"] for item in locations) or (lead.preferred_location or "your preferred location")
    bhk = lead.bhk or "the required configuration"
    return {
        "en": (
            f"Hello {name}, this is {user.username} calling from MetroCRM. "
            f"You had enquired through {source} about a {bhk} property in {location_text}. "
            "I have reviewed your requirement and would like to share some suitable property options with you."
        ),
        "hi": (
            f"नमस्ते {name} जी, मैं {user.username} MetroCRM से बात कर रहा/रही हूँ। "
            f"आपने {source} के माध्यम से {location_text} में {bhk} प्रॉपर्टी के लिए पूछताछ की थी। "
            "मैंने आपकी आवश्यकता देख ली है और आपके लिए उपयुक्त प्रॉपर्टी के कुछ विकल्प साझा करना चाहता/चाहती हूँ।"
        ),
        "hinglish": (
            f"Namaste {name} ji, main {user.username} MetroCRM se bol raha/rahi hoon. "
            f"Aapne {source} par {location_text} mein {bhk} property ke liye enquiry ki thi. "
            "Maine aapki requirement review ki hai aur aapke liye kuch suitable property options share karna chahta/chahti hoon."
        ),
    }


def _property_speeches(property_: dict[str, Any], customer: Customer | None) -> dict[str, str]:
    customer_name = (customer.name if customer else "Sir/Ma'am")
    project = property_.get("project") or "this project"
    location = property_.get("location") or "your preferred location"
    details = _speech_details(property_)

    english_details = ", ".join(value for _, value in details)
    hindi_details: list[str] = []
    hinglish_details: list[str] = []
    for label, value in details:
        raw_value = str(value)
        if label == "configuration":
            hindi_details.append(f"कॉन्फ़िगरेशन {property_.get('bhk')}")
            hinglish_details.append(f"configuration {property_.get('bhk')}")
        elif label == "carpet area":
            area = property_.get("carpet_area")
            hindi_details.append(f"कार्पेट एरिया {area:g} वर्ग फुट")
            hinglish_details.append(f"carpet area {area:g} square feet")
        elif label == "rate":
            hindi_details.append(f"रेट {_money(property_.get('price_per_sqft'))} प्रति वर्ग फुट")
            hinglish_details.append(f"rate {_money(property_.get('price_per_sqft'))} per square feet")
        elif label == "all-inclusive price":
            hindi_details.append(f"ऑल-इन्क्लूसिव कीमत {_money(property_.get('price'))}")
            hinglish_details.append(f"all-inclusive price {_money(property_.get('price'))}")
        elif label == "parking":
            hindi_details.append(f"पार्किंग {property_.get('parking')}")
            hinglish_details.append(f"parking {property_.get('parking')}")
        elif label == "negotiable":
            hindi_details.append(raw_value.replace("price is", "कीमत"))
            hinglish_details.append(raw_value)
        elif label == "possession":
            hindi_details.append(f"पजेशन {property_.get('possession')}")
            hinglish_details.append(f"possession {property_.get('possession')}")
        elif label == "RERA":
            hindi_details.append(f"RERA {property_.get('rera')}")
            hinglish_details.append(f"RERA {property_.get('rera')}")

    english = (
        f"{customer_name}, I have found a suitable option for you: {project}, located in {location}. "
        + (f"The key details are {english_details}. " if english_details else "")
        + (f"The main project highlight is: {str(property_.get('description')).strip()}. " if property_.get("description") else "")
        + "If this option looks suitable, I can explain the next steps and arrange a site visit for you."
    )
    hindi = (
        f"{customer_name} जी, आपकी आवश्यकता के अनुसार एक उपयुक्त विकल्प है: {project}, जो {location} में स्थित है। "
        + (f"इसकी मुख्य जानकारी है: {', '.join(hindi_details)}। " if hindi_details else "")
        + (f"इस प्रोजेक्ट की मुख्य विशेषता है: {str(property_.get('description')).strip()}। " if property_.get("description") else "")
        + "अगर यह विकल्प आपको उपयुक्त लगे, तो मैं आपको आगे की जानकारी दे सकता/सकती हूँ और आपके लिए साइट विज़िट भी arrange कर सकता/सकती हूँ।"
    )
    hinglish = (
        f"{customer_name} ji, aapki requirement ke according ek suitable option hai: {project}, jo {location} mein located hai. "
        + (f"Iski main details hain: {', '.join(hinglish_details)}. " if hinglish_details else "")
        + (f"Project ki main highlight hai: {str(property_.get('description')).strip()}. " if property_.get("description") else "")
        + "Agar ye option aapko suitable lage, to main aapko next steps samjha sakta/sakti hoon aur site visit bhi arrange kar sakta/sakti hoon."
    )
    return {"en": english, "hi": hindi, "hinglish": hinglish}


@router.get("/lead/{lead_id}/call", response_class=HTMLResponse)
def lead_call_assistant(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user or not _allowed(user):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead:
        return HTMLResponse("Lead not found", status_code=404)
    if not _lead_in_scope(user, lead, db):
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
        "possession_requirement": requirement.possession_requirement if requirement else None,
        "project_preference": requirement.project_preference if requirement else None,
        "developer_preference": requirement.developer_preference if requirement else None,
        "furnishing": requirement.furnishing if requirement else None,
        "parking": requirement.parking if requirement else None,
        "construction_statuses": [],
    }
    followups = db.scalars(select(FollowUp).where(FollowUp.lead_id == lead.id).order_by(FollowUp.completed.asc(), FollowUp.due_at.asc()).limit(50)).all()
    properties = _property_rows(db, customer_data)
    for item in properties:
        if not item.get("negotiable") and item.get("description"):
            try:
                meta = json.loads(item["description"]) if str(item["description"]).lstrip().startswith("{") else {}
                item["negotiable"] = meta.get("negotiable")
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    return templates.TemplateResponse("caller_lead_assistant.html", {
        "request": request, "user": user, "lead": lead, "customer": customer,
        "requirement": requirement, "locations": locations, "properties": properties, "followups": followups,
        "opening_speeches": _opening_speeches(user, lead, customer, locations),
        "property_speeches": {str(p["id"]): _property_speeches(p, customer) for p in properties},
        "csrf_token": csrf_token(request), "now": datetime.now().strftime("%d %b %Y %H:%M"), "now_datetime": datetime.now(),
    })


def _parse_optional_amount(raw: str, field_name: str) -> Decimal | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a valid amount.")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field_name} must be zero or greater.")
    return amount


@router.post("/lead/{lead_id}/requirements", dependencies=[Depends(require_csrf)])
def update_lead_requirements(
    lead_id: int, request: Request,
    customer_name: str = Form(""), mobile: str = Form(""), alternate_mobile: str = Form(""),
    email: str = Form(""), customer_notes: str = Form(""), requirement_text: str = Form(""),
    budget_min: str = Form(""), budget_max: str = Form(""), preferred_locations: str = Form(""),
    bhk: str = Form(""), property_type: str = Form(""), buy_rent: str = Form(""),
    property_category: str = Form(""), carpet_area_min: str = Form(""), carpet_area_max: str = Form(""),
    possession_requirement: str = Form(""), furnishing: str = Form(""), parking: str = Form(""),
    project_preference: str = Form(""), developer_preference: str = Form(""),
    loan_required: bool = Form(False), purpose: str = Form(""),
    requirement_notes: str = Form(""), csrf_token_value: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf_token_value)
    user = _current_user(request, db)
    if not user or not _allowed(user):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead or not _lead_in_scope(user, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    try:
        minimum = _parse_optional_amount(budget_min, "Minimum budget")
        maximum = _parse_optional_amount(budget_max, "Maximum budget")
        area_min = _parse_optional_amount(carpet_area_min, "Minimum carpet area")
        area_max = _parse_optional_amount(carpet_area_max, "Maximum carpet area")
        if minimum is not None and maximum is not None and minimum > maximum:
            return HTMLResponse("Minimum budget cannot exceed maximum budget.", status_code=400)
        if area_min is not None and area_max is not None and area_min > area_max:
            return HTMLResponse("Minimum carpet area cannot exceed maximum carpet area.", status_code=400)
    except ValueError as exc:
        return HTMLResponse(str(exc), status_code=400)
    mode = buy_rent.strip().upper()
    if mode not in {"", "BUY", "RENT", "BOTH"}:
        return HTMLResponse("Select a valid Buy / Rent option.", status_code=400)
    customer = db.get(Customer, lead.customer_id) if lead.customer_id else None
    name = customer_name.strip() or (customer.name if customer else "")
    if not name:
        return HTMLResponse("Customer name is required.", status_code=400)
    if customer is None:
        customer = Customer(name=name)
        db.add(customer)
        db.flush()
        lead.customer_id = customer.id
    customer.name = name[:200]
    customer.mobile = mobile.strip()[:30] or None
    customer.alternate_mobile = alternate_mobile.strip()[:30] or None
    customer.email = email.strip().lower()[:255] or None
    customer.notes = customer_notes.strip() or None

    locations = [item.strip() for item in preferred_locations.split(",") if item.strip()]
    lead.requirement = requirement_text.strip() or None
    lead.budget_min = minimum
    lead.budget_max = maximum
    lead.preferred_location = ", ".join(locations) or None
    lead.bhk = bhk.strip() or None
    lead.property_type = property_type.strip() or None
    lead.buy_rent = mode or None

    requirement = db.scalar(
        select(CustomerRequirement)
        .where(CustomerRequirement.customer_id == customer.id, CustomerRequirement.is_active.is_(True))
        .order_by(CustomerRequirement.updated_at.desc()).limit(1)
    )
    if requirement is None:
        requirement = CustomerRequirement(customer_id=customer.id, is_active=True)
        db.add(requirement)
    existing_locations = {}
    try:
        for item in json.loads(requirement.locations_json or "[]"):
            if isinstance(item, dict) and item.get("name"):
                existing_locations[str(item["name"]).casefold()] = item
    except (TypeError, ValueError, json.JSONDecodeError):
        existing_locations = {}
    requirement.locations_json = json.dumps([
        {
            "name": name,
            "side": existing_locations.get(name.casefold(), {}).get("side", "Both"),
            "priority": existing_locations.get(name.casefold(), {}).get("priority", "Primary"),
        }
        for name in locations
    ])
    requirement.buy_rent = mode or None
    requirement.property_category = property_category.strip()[:50] or None
    requirement.budget_min = minimum
    requirement.budget_max = maximum
    requirement.carpet_area_min = area_min
    requirement.carpet_area_max = area_max
    requirement.bhk = lead.bhk
    requirement.property_type = lead.property_type
    requirement.possession_requirement = possession_requirement.strip()[:100] or None
    requirement.furnishing = furnishing.strip()[:50] or None
    requirement.parking = parking.strip()[:100] or None
    requirement.project_preference = project_preference.strip()[:1000] or None
    requirement.developer_preference = developer_preference.strip()[:1000] or None
    requirement.loan_required = bool(loan_required)
    requirement.purpose = purpose.strip()[:100] or None
    requirement.notes = requirement_notes.strip() or None
    requirement.updated_at = datetime.now()
    db.add(AuditEvent(actor_user_id=user.id, action="LEAD_REQUIREMENTS_UPDATED", entity_type="Lead", entity_id=str(lead.id), details=json.dumps({"customer_id": customer.id, "requirement_updated": True})))
    db.commit()
    return RedirectResponse(f"/caller/lead/{lead.id}/call", status_code=303)


@router.post("/lead/{lead_id}/follow-ups", dependencies=[Depends(require_csrf)])
def schedule_lead_followup(
    lead_id: int, request: Request, due_at: str = Form(...),
    purpose: str = Form("Call follow-up"), notes: str = Form(""),
    csrf_token_value: str = Form("", alias="csrf_token"), db: Session = Depends(get_db),
):
    require_csrf(request, csrf_token_value)
    user = _current_user(request, db)
    if not user or not _allowed(user):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead or not _lead_in_scope(user, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    try:
        scheduled = datetime.fromisoformat(due_at)
    except ValueError:
        return HTMLResponse("Enter a valid follow-up date and time.", status_code=400)
    if not lead.customer_id:
        return HTMLResponse("Link a customer to this lead before scheduling a follow-up.", status_code=400)
    followup = FollowUp(
        lead_id=lead.id, customer_id=lead.customer_id,
        assigned_user_id=lead.assigned_user_id or user.id, due_at=scheduled,
        purpose=purpose.strip()[:255] or "Call follow-up",
        notes=notes.strip() or None, completed=False,
    )
    db.add(followup)
    db.add(AuditEvent(actor_user_id=user.id, action="LEAD_FOLLOWUP_SCHEDULED", entity_type="Lead", entity_id=str(lead.id), details=json.dumps({"followup_due_at": scheduled.isoformat()})))
    db.commit()
    return RedirectResponse(f"/caller/lead/{lead.id}/call", status_code=303)


@router.post("/lead/{lead_id}/follow-ups/{followup_id}/complete", dependencies=[Depends(require_csrf)])
def complete_lead_followup(
    lead_id: int, followup_id: int, request: Request,
    csrf_token_value: str = Form("", alias="csrf_token"), db: Session = Depends(get_db),
):
    require_csrf(request, csrf_token_value)
    user = _current_user(request, db)
    if not user or not _allowed(user):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead or not _lead_in_scope(user, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    followup = db.get(FollowUp, followup_id)
    if not followup or followup.lead_id != lead.id:
        return HTMLResponse("Follow-up not found for this lead.", status_code=404)
    followup.completed = True
    db.add(AuditEvent(actor_user_id=user.id, action="LEAD_FOLLOWUP_COMPLETED", entity_type="Lead", entity_id=str(lead.id), details=json.dumps({"followup_id": followup.id})))
    db.commit()
    return RedirectResponse(f"/caller/lead/{lead.id}/call", status_code=303)
