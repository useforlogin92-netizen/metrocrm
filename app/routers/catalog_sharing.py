"""Customer-facing property catalog sharing API and preview UI."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import Access, Role, user_allows
from app.services.catalog_sharing import ContactSelection, build_share_payload

router = APIRouter(prefix="/catalog", tags=["catalog-sharing"])
templates = Jinja2Templates(directory="app/templates")


def _current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user


def _can_share(user: User) -> bool:
    try:
        role = Role(user.role)
    except ValueError:
        return False
    try:
        permissions = json.loads(user.permissions_json or "{}")
    except (json.JSONDecodeError, TypeError):
        permissions = {}
    if not isinstance(permissions, Mapping):
        permissions = {}
    return user_allows(role, "properties", Access.VIEW, permissions)


def _require_sharing_user(request: Request, db: Session) -> User:
    user = _current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication_required")
    if not _can_share(user):
        raise HTTPException(status_code=403, detail="catalog_sharing_not_permitted")
    return user


class ContactSelectionRequest(BaseModel):
    contact_type: str
    fields: list[str] = Field(default_factory=list)


class CatalogShareRequest(BaseModel):
    property_data: dict[str, Any]
    selected_fields: list[str] = Field(default_factory=list)
    selected_media_ids: list[str] = Field(default_factory=list)
    media: list[dict[str, Any]] = Field(default_factory=list)
    contacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    contact_selections: list[ContactSelectionRequest] = Field(default_factory=list)


def _payload(request: CatalogShareRequest) -> dict[str, Any]:
    selections = tuple(
        ContactSelection(item.contact_type, frozenset(item.fields))
        for item in request.contact_selections
    )
    return build_share_payload(
        request.property_data,
        selected_fields=frozenset(request.selected_fields),
        selected_media_ids=frozenset(request.selected_media_ids),
        media=request.media,
        contacts=request.contacts,
        contact_selections=selections,
    )


@router.get("/share", response_class=HTMLResponse, response_model=None)
def share_catalog_page(request: Request, db: Session = Depends(get_db)) -> Response:
    """Render the explicit field/media/contact selection screen for staff."""
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    if not _can_share(user):
        return HTMLResponse("Catalog sharing is not permitted for this account.", status_code=403)
    return templates.TemplateResponse("catalog_share.html", {"request": request})


@router.post("/preview")
def preview_catalog_share(request: Request, body: CatalogShareRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Preview exactly what would be shared, after server-side sanitization."""
    _require_sharing_user(request, db)
    return _payload(body)


@router.post("/share")
def share_catalog(request: Request, body: CatalogShareRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return the sanitized share payload for the future delivery provider."""
    _require_sharing_user(request, db)
    return {"status": "READY", "catalog": _payload(body)}
