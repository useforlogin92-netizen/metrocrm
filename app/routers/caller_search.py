from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


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


def _inventory_rows(db: Session, city: str) -> list[dict[str, Any]]:
    """Adapt Unit + Project data into the caller-search matching contract."""
    stmt = select(Unit, Project, Tower).join(Project, Unit.project_id == Project.id).outerjoin(Tower, Unit.tower_id == Tower.id)
    if city:
        stmt = stmt.where(Project.city.ilike(city.strip()))
    rows: list[dict[str, Any]] = []
    for unit, project, tower in db.execute(stmt).all():
        station, corridor = _station_metadata(" ".join(filter(None, [project.locality, project.address, project.sector])))
        side = "Both"
        location_text = " ".join(filter(None, [project.locality, project.sector, project.address]))
        lowered = location_text.casefold()
        if " west" in lowered or lowered.endswith("west"):
            side = "West"
        elif " east" in lowered or lowered.endswith("east"):
            side = "East"
        possession_date = unit.possession or project.possession_date
        rows.append({
            "id": unit.id, "title": f"{project.name} - {unit.unit_number}", "project": project.name,
            "developer_id": project.developer_id, "tower": tower.name if tower else None, "unit_number": unit.unit_number,
            "city": project.city, "district": project.district, "state": project.state, "locality": project.locality,
            "location": location_text, "sector": project.sector, "pincode": project.pincode, "station": station,
            "railway_station": station, "corridor": corridor, "side": side, "bhk": unit.bhk,
            "property_type": unit.property_type, "carpet_area": _decimal(unit.carpet_area), "price": _decimal(unit.price),
            "price_per_sqft": _decimal(unit.price_per_sqft), "construction_status": project.construction_status or unit.status or unit.availability,
            "possession": unit.possession, "possession_date": possession_date, "rera_possession_date": project.possession_date,
            "rera": unit.rera or project.rera, "parking": unit.parking, "facing": unit.facing, "furnishing": unit.furnishing,
            "amenities": _json_list(unit.amenities_json) + _json_list(project.amenities_json),
            "photos": _json_list(unit.photos_json) + _json_list(project.photos_json), "floor_plan": unit.floor_plan,
            "brochure": unit.brochure or project.brochure, "description": unit.description or project.description,
        })
    return rows


@router.get("/options")
def caller_search_options(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user or not user.is_active:
        return {"error": "authentication_required"}
    corridors: dict[str, list[str]] = {}
    for station in MUMBAI_LOCAL_STATIONS:
        corridors.setdefault(station["corridor"], []).append(station["name"])
    return {
        "corridors": corridors,
        "stations": MUMBAI_LOCAL_STATIONS,
        "bhk": BHK_OPTIONS,
        "jodi": JODI_OPTIONS,
        "construction": CONSTRUCTION_OPTIONS,
        "side": SIDE_OPTIONS,
        "budget_slabs": [{"label": label, "min": low, "max": high} for label, low, high in BUDGET_SLABS],
        "possession_years": list(range(2026, 2051)),
    }


@router.get("/search", response_class=HTMLResponse, response_model=None)
def caller_search_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    user = _user(request, db)
    if not user or not user.is_active:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("caller_search.html", {"request": request})


@router.post("/search")
def caller_search(body: CallerSearchRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user or not user.is_active:
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
        item.update({
            "title": property_data.get("title"), "project": property_data.get("project"),
            "locality": property_data.get("locality"), "bhk": property_data.get("bhk"),
            "property_type": property_data.get("property_type"), "price": property_data.get("price"),
            "carpet_area": property_data.get("carpet_area"), "construction_status": property_data.get("construction_status"),
            "possession": property_data.get("possession"), "photos": property_data.get("photos", [])[:1],
        })
        response_results.append(item)
    return {"count": len(response_results), "results": response_results}
