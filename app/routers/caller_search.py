from __future__ import annotations

import json
import re
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.catalog_models import PropertyMedia
from app.csrf import csrf_token, require_csrf_header
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, Project, PropertyConfiguration, Tower, Unit, User
from app.location_catalog import MUMBAI_LOCAL_STATIONS
from app.services.caller_search import BHK_OPTIONS, BUDGET_SLABS, CONSTRUCTION_OPTIONS, JODI_OPTIONS, SIDE_OPTIONS, filter_and_rank_properties
from app.services.property_pricing import format_property_value, format_rate_per_sqft

router = APIRouter(prefix="/caller", tags=["caller-search"])
templates = Jinja2Templates(directory="app/templates")

CALLER_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}


def _can_use_search(user: User | None) -> bool:
    return bool(user and user.role in CALLER_ROLES)


class LeadSearchRequest(BaseModel):
    query: str = Field(default="", max_length=200)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    bhk: str = Field(default="", max_length=30)
    location: str = Field(default="", max_length=200)
    lead_status: str = Field(default="", max_length=40)


class LeadDispositionRequest(BaseModel):
    status: str = Field(min_length=1, max_length=50)
    notes: str = Field(default="", max_length=4000)


class CallerSearchRequest(BaseModel):
    city: str = "Mumbai"
    mumbai_corridor: str | None = None
    mumbai_station_from: str | None = None
    mumbai_station_to: str | None = None
    mumbai_side: str = "Both"
    bhk: list[str] = Field(default_factory=list)
    jodi: list[str] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    property_type: str | None = None
    construction_statuses: list[str] = Field(default_factory=list)
    possession_by: int | None = None
    preferred_locations: list[str] = Field(default_factory=list)


def _user(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _station_metadata(text: str | None) -> tuple[str | None, str]:
    haystack = str(text or "").casefold()
    for item in MUMBAI_LOCAL_STATIONS:
        if item["name"].casefold() in haystack:
            return item["name"], item["corridor"]
    return None, ""


def _decimal(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _project_catalog_details(description: str | None) -> dict[str, Any]:
    text = str(description or "")
    bhk_match = re.search(r"(\d+)\s*BHK", text, re.IGNORECASE)
    area_match = re.search(r"area\s+([0-9]+(?:\s*[-/]\s*[0-9]+)?)\s*(?:sq\.?\s*ft)?", text, re.IGNORECASE)
    price_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*Cr\b", text, re.IGNORECASE)
    possession_match = re.search(r"possession\s+([^|]+)", text, re.IGNORECASE)
    return {
        "bhk": f"{bhk_match.group(1)} BHK" if bhk_match else None,
        "carpet_area": float(re.split(r"[-/]", area_match.group(1))[0].strip()) if area_match else None,
        "price": float(price_match.group(1)) * 10_000_000 if price_match else None,
        "possession": possession_match.group(1).strip()[:100] if possession_match else None,
    }


def _project_media(db: Session, project_id: int, unit_id: int | None = None) -> list[str]:
    media = db.scalars(select(PropertyMedia).where(PropertyMedia.project_id == project_id, (PropertyMedia.unit_id == unit_id) | PropertyMedia.unit_id.is_(None)).order_by(PropertyMedia.sort_order.asc(), PropertyMedia.id.asc())).all()
    return [m.file_url for m in media if m.file_url]


def _project_level_rows(db: Session, city: str) -> list[dict[str, Any]]:
    stmt = select(Project).order_by(Project.id.desc())
    if city:
        stmt = stmt.where(Project.city.ilike(city.strip()))
    rows: list[dict[str, Any]] = []
    for project in db.scalars(stmt).all():
        station, corridor = _station_metadata(" ".join(filter(None, [project.locality, project.address, project.sector])))
        location_text = " ".join(filter(None, [project.locality, project.sector, project.address]))
        lowered = location_text.casefold()
        side = "West" if " west" in lowered or lowered.endswith("west") else "East" if " east" in lowered or lowered.endswith("east") else "Both"
        photos = _project_media(db, project.id) or _json_list(project.photos_json)
        details = _project_catalog_details(project.description)
        rows.append({
            "id": project.id, "title": project.name, "project": project.name, "developer_id": project.developer_id,
            "tower": None, "unit_number": None, "city": project.city, "district": project.district, "state": project.state,
            "locality": project.locality, "location": location_text, "sector": project.sector, "pincode": project.pincode,
            "station": station, "railway_station": station, "corridor": corridor, "side": side, "bhk": details["bhk"],
            "property_type": "Project", "carpet_area": details["carpet_area"], "price": details["price"], "price_per_sqft": None,
            "construction_status": project.construction_status, "possession": project.possession_date or details["possession"],
            "possession_date": project.possession_date, "rera_possession_date": project.possession_date, "rera": project.rera,
            "parking": None, "facing": None, "furnishing": None, "amenities": _json_list(project.amenities_json),
            "photos": photos, "floor_plan": None, "brochure": project.brochure, "description": project.description,
        })
    return rows


def _configuration_rows(db: Session, city: str) -> list[dict[str, Any]]:
    stmt = (
        select(PropertyConfiguration, Project)
        .join(Project, PropertyConfiguration.project_id == Project.id)
        .order_by(Project.id.desc(), PropertyConfiguration.sort_order.asc(), PropertyConfiguration.id.asc())
    )
    if city:
        stmt = stmt.where(Project.city.ilike(city.strip()))
    rows: list[dict[str, Any]] = []
    for config, project in db.execute(stmt).all():
        station, corridor = _station_metadata(" ".join(filter(None, [project.locality, project.address, project.sector])))
        location_text = " ".join(filter(None, [project.locality, project.sector, project.address]))
        lowered = location_text.casefold()
        side = "West" if " west" in lowered or lowered.endswith("west") else "East" if " east" in lowered or lowered.endswith("east") else "Both"
        photos = _project_media(db, project.id) or _json_list(project.photos_json)
        rows.append({
            "id": -config.id,
            "configuration_id": config.id,
            "title": f"{project.name} - {config.configuration}",
            "project": project.name,
            "developer_id": project.developer_id,
            "tower": None,
            "unit_number": None,
            "city": project.city,
            "district": project.district,
            "state": project.state,
            "locality": project.locality,
            "location": location_text,
            "sector": project.sector,
            "pincode": project.pincode,
            "station": station,
            "railway_station": station,
            "corridor": corridor,
            "side": side,
            "bhk": config.configuration,
            "property_type": "Configuration",
            "carpet_area": _decimal(config.carpet_area),
            "price": _decimal(config.price_including_all),
            "price_per_sqft": _decimal(config.rate_per_sqft),
            "construction_status": project.construction_status or config.availability,
            "possession": project.possession_date,
            "possession_date": project.possession_date,
            "rera_possession_date": project.possession_date,
            "rera": project.rera,
            "parking": None,
            "facing": None,
            "furnishing": None,
            "amenities": _json_list(project.amenities_json),
            "photos": photos,
            "floor_plan": None,
            "brochure": project.brochure,
            "description": project.description,
            "availability": config.availability,
            "negotiation": config.negotiation,
        })
    return rows


def _inventory_rows(db: Session, city: str) -> list[dict[str, Any]]:
    stmt = select(Unit, Project, Tower).join(Project, Unit.project_id == Project.id).outerjoin(Tower, Unit.tower_id == Tower.id)
    if city:
        stmt = stmt.where(Project.city.ilike(city.strip()))
    rows: list[dict[str, Any]] = []
    project_ids_with_units: set[int] = set()
    for unit, project, tower in db.execute(stmt).all():
        project_ids_with_units.add(project.id)
        station, corridor = _station_metadata(" ".join(filter(None, [project.locality, project.address, project.sector])))
        location_text = " ".join(filter(None, [project.locality, project.sector, project.address]))
        lowered = location_text.casefold()
        side = "West" if " west" in lowered or lowered.endswith("west") else "East" if " east" in lowered or lowered.endswith("east") else "Both"
        possession_date = unit.possession or project.possession_date
        photos = _project_media(db, project.id, unit.id) or (_json_list(unit.photos_json) + _json_list(project.photos_json))
        rows.append({
            "id": unit.id, "title": f"{project.name} - {unit.unit_number}", "project": project.name, "developer_id": project.developer_id,
            "tower": tower.name if tower else None, "unit_number": unit.unit_number, "city": project.city, "district": project.district,
            "state": project.state, "locality": project.locality, "location": location_text, "sector": project.sector, "pincode": project.pincode,
            "station": station, "railway_station": station, "corridor": corridor, "side": side, "bhk": unit.bhk,
            "property_type": unit.property_type, "carpet_area": _decimal(unit.carpet_area), "price": _decimal(unit.price),
            "price_per_sqft": _decimal(unit.price_per_sqft), "construction_status": project.construction_status or unit.status or unit.availability,
            "possession": unit.possession, "possession_date": possession_date, "rera_possession_date": project.possession_date,
            "rera": unit.rera or project.rera, "parking": unit.parking, "facing": unit.facing, "furnishing": unit.furnishing,
            "amenities": _json_list(unit.amenities_json) + _json_list(project.amenities_json), "photos": photos, "floor_plan": unit.floor_plan,
            "brochure": unit.brochure or project.brochure, "description": unit.description or project.description,
        })
    configuration_rows = [row for row in _configuration_rows(db, city) if row["project"] not in {item["project"] for item in rows}]
    rows.extend(configuration_rows)
    configured_project_names = {row["project"] for row in configuration_rows}
    for project_row in _project_level_rows(db, city):
        if project_row["id"] not in project_ids_with_units and project_row["project"] not in configured_project_names:
            rows.append(project_row)
    return rows


def _visible_lead_user_ids(user: User, db: Session) -> set[int] | None:
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        return None
    visible = {user.id}
    if user.role in {"MANAGER", "TL"}:
        frontier = {user.id}
        while frontier:
            children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
            frontier = {int(uid) for uid in children if int(uid) not in visible}
            visible.update(frontier)
    return visible


_LEAD_STATUS_GROUPS = {
    "HOT": {"QUALIFIED", "SITE_VISIT_SCHEDULED", "NEGOTIATION", "BOOKED"},
    "WARM": {"CONTACTED", "FOLLOW_UP_REQUIRED"},
    "COLD": {"LOST", "NOT_INTERESTED"},
    "SITE_VISIT_BOOKED": {"SITE_VISIT_SCHEDULED"},
}
_ALLOWED_DISPOSITION_STATUSES = {
    "NEW", "CONTACTED", "QUALIFIED", "FOLLOW_UP_REQUIRED", "SITE_VISIT_SCHEDULED",
    "NEGOTIATION", "BOOKED", "LOST", "NOT_INTERESTED", "INVALID", "DUPLICATE", "CLOSED",
}


@router.post("/search/leads")
def search_leads(body: LeadSearchRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication_required")
    if not _can_use_search(user):
        raise HTTPException(status_code=403, detail="caller_search_not_permitted")

    stmt = select(Lead, Customer, User).outerjoin(Customer, Lead.customer_id == Customer.id).outerjoin(User, Lead.assigned_user_id == User.id).order_by(Lead.created_at.desc()).limit(300)
    visible_ids = _visible_lead_user_ids(user, db)
    if visible_ids is not None:
        if user.role in {"MANAGER", "TL"}:
            stmt = stmt.where(or_(Lead.assigned_user_id.in_(visible_ids), Lead.assigned_user_id.is_(None)))
        else:
            stmt = stmt.where(Lead.assigned_user_id == user.id)

    query = body.query.strip()
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(or_(Customer.name.ilike(pattern), Customer.mobile.ilike(pattern), Customer.alternate_mobile.ilike(pattern), Customer.email.ilike(pattern), Lead.source.ilike(pattern)))
    if body.budget_min is not None:
        stmt = stmt.where(or_(Lead.budget_max.is_(None), Lead.budget_max >= body.budget_min))
    if body.budget_max is not None:
        stmt = stmt.where(or_(Lead.budget_min.is_(None), Lead.budget_min <= body.budget_max))
    if body.bhk.strip():
        stmt = stmt.where(Lead.bhk.ilike(f"%{body.bhk.strip()}%"))
    if body.location.strip():
        stmt = stmt.where(Lead.preferred_location.ilike(f"%{body.location.strip()}%"))
    status_key = body.lead_status.strip().upper().replace(" ", "_").replace("-", "_")
    if status_key in _LEAD_STATUS_GROUPS:
        stmt = stmt.where(Lead.status.in_(_LEAD_STATUS_GROUPS[status_key]))
    elif status_key:
        stmt = stmt.where(Lead.status == status_key)

    results = []
    for lead, customer, assigned_user in db.execute(stmt).all():
        mobile = customer.mobile if customer else None
        results.append({
            "id": lead.id,
            "name": customer.name if customer else "Unlinked customer",
            "mobile": mobile,
            "alternate_mobile": customer.alternate_mobile if customer else None,
            "email": customer.email if customer else None,
            "source": lead.source,
            "status": lead.status,
            "budget_min": float(lead.budget_min) if lead.budget_min is not None else None,
            "budget_max": float(lead.budget_max) if lead.budget_max is not None else None,
            "preferred_location": lead.preferred_location,
            "bhk": lead.bhk,
            "assigned_to": assigned_user.username if assigned_user else "Unassigned",
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        })
    return {"count": len(results), "results": results}


@router.post("/search/leads/{lead_id}/disposition", dependencies=[Depends(require_csrf_header)])
def save_lead_disposition(
    lead_id: int, body: LeadDispositionRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    user = _user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication_required")
    if not _can_use_search(user):
        raise HTTPException(status_code=403, detail="caller_search_not_permitted")
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead_not_found")
    visible_ids = _visible_lead_user_ids(user, db)
    if visible_ids is not None and lead.assigned_user_id not in visible_ids:
        raise HTTPException(status_code=404, detail="lead_not_found")
    normalized = body.status.strip().upper().replace(" ", "_").replace("-", "_")
    if normalized not in _ALLOWED_DISPOSITION_STATUSES:
        raise HTTPException(status_code=422, detail="invalid_lead_status")
    previous_status = lead.status
    lead.status = normalized
    details = {"previous_status": previous_status, "new_status": normalized, "notes": body.notes.strip()}
    db.add(AuditEvent(
        actor_user_id=user.id,
        action="LEAD_DISPOSITION_UPDATED",
        entity_type="Lead",
        entity_id=str(lead.id),
        details=json.dumps(details, ensure_ascii=False),
    ))
    db.commit()
    return {"success": True, "lead_id": lead.id, "status": lead.status}


@router.get("/options")
def caller_search_options(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication_required")
    if not _can_use_search(user):
        raise HTTPException(status_code=403, detail="caller_search_not_permitted")
    corridors: dict[str, list[str]] = {}
    for station in MUMBAI_LOCAL_STATIONS:
        corridors.setdefault(station["corridor"], []).append(station["name"])
    return {"corridors": corridors, "stations": MUMBAI_LOCAL_STATIONS, "bhk": BHK_OPTIONS, "jodi": JODI_OPTIONS, "construction": CONSTRUCTION_OPTIONS, "side": SIDE_OPTIONS, "budget_slabs": [{"label": label, "min": low, "max": high} for label, low, high in BUDGET_SLABS], "possession_years": list(range(2026, 2051))}


@router.get("/search", response_class=HTMLResponse, response_model=None)
def caller_search_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    user = _user(request, db)
    if not user or not _can_use_search(user):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "caller_search.html", {"request": request, "username": user.username, "role": user.role, "avatar": user.username[:1].upper(), "active_page": "caller", "show_integrations": user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}, "show_alerts": user.role in {"SUPER_ADMIN", "ADMIN"}, "show_approvals": user.role in {"SUPER_ADMIN", "ADMIN"}, "csrf_token": csrf_token(request)})


@router.post("/search")
def caller_search(body: CallerSearchRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication_required")
    if not _can_use_search(user):
        raise HTTPException(status_code=403, detail="caller_search_not_permitted")
    properties = _inventory_rows(db, body.city)
    filters = body.model_dump(exclude_none=True)
    if body.jodi:
        filters["bhk"] = body.bhk + body.jodi
    results = filter_and_rank_properties(filters, properties)
    by_id = {str(item["id"]): item for item in properties}
    response_results = []
    for result in results:
        item = asdict(result)
        property_data = by_id.get(str(result.property_id), {})
        price = property_data.get("price")
        rate = property_data.get("price_per_sqft")
        item.update({
            "title": property_data.get("title"), "project": property_data.get("project"), "developer_id": property_data.get("developer_id"),
            "tower": property_data.get("tower"), "unit_number": property_data.get("unit_number"), "city": property_data.get("city"),
            "district": property_data.get("district"), "state": property_data.get("state"), "locality": property_data.get("locality"),
            "location": property_data.get("location"), "sector": property_data.get("sector"), "pincode": property_data.get("pincode"),
            "station": property_data.get("station"), "railway_station": property_data.get("railway_station"), "corridor": property_data.get("corridor"),
            "side": property_data.get("side"), "bhk": property_data.get("bhk"), "property_type": property_data.get("property_type"),
            "price": price, "price_display": format_property_value(price) if price is not None else "Price on request",
            "carpet_area": property_data.get("carpet_area"), "price_per_sqft": rate,
            "price_per_sqft_display": format_rate_per_sqft(rate) if rate is not None else "",
            "construction_status": property_data.get("construction_status"), "possession": property_data.get("possession"),
            "possession_date": property_data.get("possession_date"), "rera_possession_date": property_data.get("rera_possession_date"),
            "rera": property_data.get("rera"), "parking": property_data.get("parking"), "facing": property_data.get("facing"),
            "furnishing": property_data.get("furnishing"), "amenities": property_data.get("amenities", []), "photos": property_data.get("photos", []),
            "floor_plan": property_data.get("floor_plan"), "brochure": property_data.get("brochure"), "description": property_data.get("description"),
        })
        response_results.append(item)
    return {"count": len(response_results), "results": response_results}
