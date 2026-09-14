from __future__ import annotations

import json
import re
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import PropertyMedia
from app.database import get_db
from app.models import Project, Tower, Unit, User
from app.location_catalog import MUMBAI_LOCAL_STATIONS
from app.services.caller_search import BHK_OPTIONS, BUDGET_SLABS, CONSTRUCTION_OPTIONS, JODI_OPTIONS, SIDE_OPTIONS, filter_and_rank_properties

router = APIRouter(prefix="/caller", tags=["caller-search"])
templates = Jinja2Templates(directory="app/templates")


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
    for project_row in _project_level_rows(db, city):
        if project_row["id"] not in project_ids_with_units:
            rows.append(project_row)
    return rows


@router.get("/options")
def caller_search_options(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user:
        return {"error": "authentication_required"}
    corridors: dict[str, list[str]] = {}
    for station in MUMBAI_LOCAL_STATIONS:
        corridors.setdefault(station["corridor"], []).append(station["name"])
    return {"corridors": corridors, "stations": MUMBAI_LOCAL_STATIONS, "bhk": BHK_OPTIONS, "jodi": JODI_OPTIONS, "construction": CONSTRUCTION_OPTIONS, "side": SIDE_OPTIONS, "budget_slabs": [{"label": label, "min": low, "max": high} for label, low, high in BUDGET_SLABS], "possession_years": list(range(2026, 2051))}


@router.get("/search", response_class=HTMLResponse, response_model=None)
def caller_search_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    user = _user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("caller_search.html", {"request": request, "username": user.username, "role": user.role, "avatar": user.username[:1].upper(), "active_page": "caller", "show_integrations": user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}, "show_alerts": user.role in {"SUPER_ADMIN", "ADMIN"}, "show_approvals": user.role in {"SUPER_ADMIN", "ADMIN"}})


@router.post("/search")
def caller_search(body: CallerSearchRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user:
        return {"error": "authentication_required"}
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
        # Return the complete caller-safe property payload, not only the
        # headline fields used by the result cards. This lets the UI and AI
        # caller speech show every available CRM detail.
        item.update({
            "title": property_data.get("title"), "project": property_data.get("project"), "developer_id": property_data.get("developer_id"),
            "tower": property_data.get("tower"), "unit_number": property_data.get("unit_number"), "city": property_data.get("city"),
            "district": property_data.get("district"), "state": property_data.get("state"), "locality": property_data.get("locality"),
            "location": property_data.get("location"), "sector": property_data.get("sector"), "pincode": property_data.get("pincode"),
            "station": property_data.get("station"), "railway_station": property_data.get("railway_station"), "corridor": property_data.get("corridor"),
            "side": property_data.get("side"), "bhk": property_data.get("bhk"), "property_type": property_data.get("property_type"),
            "price": property_data.get("price"), "carpet_area": property_data.get("carpet_area"), "price_per_sqft": property_data.get("price_per_sqft"),
            "construction_status": property_data.get("construction_status"), "possession": property_data.get("possession"),
            "possession_date": property_data.get("possession_date"), "rera_possession_date": property_data.get("rera_possession_date"),
            "rera": property_data.get("rera"), "parking": property_data.get("parking"), "facing": property_data.get("facing"),
            "furnishing": property_data.get("furnishing"), "amenities": property_data.get("amenities", []), "photos": property_data.get("photos", []),
            "floor_plan": property_data.get("floor_plan"), "brochure": property_data.get("brochure"), "description": property_data.get("description"),
        })
        response_results.append(item)
    return {"count": len(response_results), "results": response_results}
