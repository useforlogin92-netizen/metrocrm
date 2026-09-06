from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.caller_search import filter_and_rank_properties

router = APIRouter(prefix="/caller", tags=["caller-search"])
templates = Jinja2Templates(directory="app/templates")

class CallerSearchRequest(BaseModel):
    city: str = "Mumbai"
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

@router.get("/search", response_class=HTMLResponse, response_model=None)
def caller_search_page(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user or not user.is_active:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("caller_search.html", {"request": request})

@router.post("/search")
def caller_search(body: CallerSearchRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _user(request, db)
    if not user or not user.is_active:
        return {"error": "authentication_required"}
    # Inventory adapter: production DB property rows can be mapped here without
    # exposing internal/customer fields to the caller UI.
    properties: list[dict[str, Any]] = []
    filters = body.model_dump(exclude_none=True)
    if body.jodi:
        filters["bhk"] = body.bhk + body.jodi
    results = filter_and_rank_properties(filters, properties)
    return {"count": len(results), "results": [r.__dict__ for r in results]}
