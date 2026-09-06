"""Customer-facing property catalog sharing with explicit selections and secure links."""
from __future__ import annotations
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.catalog_models import CatalogShare, CatalogShareVisit
from app.integration_models import PropertyVisitAlert
from app.models import AuditEvent, User
from app.permissions import Access, Role, user_allows
from app.services.catalog_sharing import ContactSelection, build_share_payload

router = APIRouter(prefix="/catalog", tags=["catalog-sharing"])
templates = Jinja2Templates(directory="app/templates")


def _current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    return user if user and user.is_active else None


def _can_share(user: User) -> bool:
    try:
        role = Role(user.role)
        permissions = json.loads(user.permissions_json or "{}")
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    return isinstance(permissions, Mapping) and user_allows(role, "properties", Access.VIEW, permissions)


def _require_sharing_user(request: Request, db: Session) -> User:
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401, "authentication_required")
    if not _can_share(user):
        raise HTTPException(403, "catalog_sharing_not_permitted")
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
    project_id: int | None = None
    unit_id: int | None = None
    expires_hours: int | None = Field(default=None, ge=1, le=720)


def _payload(request: CatalogShareRequest) -> dict[str, Any]:
    selections = tuple(ContactSelection(item.contact_type, frozenset(item.fields)) for item in request.contact_selections)
    return build_share_payload(request.property_data, selected_fields=frozenset(request.selected_fields), selected_media_ids=frozenset(request.selected_media_ids), media=request.media, contacts=request.contacts, contact_selections=selections)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.get("/share", response_class=HTMLResponse, response_model=None)
def share_catalog_page(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    if not _can_share(user):
        return HTMLResponse("Catalog sharing is not permitted for this account.", status_code=403)
    return templates.TemplateResponse("catalog_share.html", {"request": request})


@router.post("/preview")
def preview_catalog_share(request: Request, body: CatalogShareRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_sharing_user(request, db)
    return _payload(body)


@router.post("/share")
def share_catalog(request: Request, body: CatalogShareRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _require_sharing_user(request, db)
    payload = _payload(body)
    token = secrets.token_urlsafe(32)
    share = CatalogShare(token_hash=_token_hash(token), project_id=body.project_id, unit_id=body.unit_id, payload_json=json.dumps(payload, default=str), created_by_id=user.id, expires_at=(datetime.utcnow() + timedelta(hours=body.expires_hours)) if body.expires_hours else None)
    db.add(share)
    db.add(AuditEvent(actor_user_id=user.id, action="CATALOG_SHARE_CREATED", entity_type="CatalogShare", entity_id="pending", details=json.dumps({"project_id": body.project_id, "unit_id": body.unit_id})))
    db.commit(); db.refresh(share)
    return {"status": "READY", "share_id": share.id, "share_token": token, "share_path": f"/catalog/view/{token}", "catalog": payload}


@router.get("/view/{token}", response_class=HTMLResponse)
def public_catalog(token: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    share = db.scalar(select(CatalogShare).where(CatalogShare.token_hash == _token_hash(token), CatalogShare.active.is_(True)))
    if not share or (share.expires_at and share.expires_at < datetime.utcnow()):
        raise HTTPException(404, "catalog_link_not_found_or_expired")
    payload = json.loads(share.payload_json)
    return templates.TemplateResponse("catalog_public.html", {"request": request, "catalog": payload, "visit_url": f"/catalog/view/{token}/visit"})


@router.post("/view/{token}/visit")
async def public_catalog_visit(token: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    share = db.scalar(select(CatalogShare).where(CatalogShare.token_hash == _token_hash(token), CatalogShare.active.is_(True)))
    if not share or (share.expires_at and share.expires_at < datetime.utcnow()):
        raise HTTPException(404, "catalog_link_not_found_or_expired")
    client_ip = request.client.host if request.client else "unknown"
    visitor_hash = hashlib.sha256((settings.secret_key + client_ip).encode()).hexdigest()
    recent = db.scalar(select(CatalogShareVisit).where(CatalogShareVisit.share_id == share.id, CatalogShareVisit.visitor_key_hash == visitor_hash, CatalogShareVisit.created_at >= datetime.utcnow() - timedelta(seconds=settings.property_visit_alert_cooldown_seconds)))
    if recent:
        return {"status": "already_recorded"}
    db.add(CatalogShareVisit(share_id=share.id, visitor_key_hash=visitor_hash, user_agent=(request.headers.get("user-agent") or "")[:500], page_url=str(request.headers.get("referer") or "")[:1000]))
    db.add(PropertyVisitAlert(project_id=share.project_id, unit_id=share.unit_id, visitor_ip_hash=visitor_hash, user_agent=(request.headers.get("user-agent") or "")[:500], page_url=f"/catalog/view/{token}"))
    db.add(AuditEvent(action="PROPERTY_CATALOG_VISIT", entity_type="CatalogShare", entity_id=str(share.id), details=json.dumps({"project_id": share.project_id, "unit_id": share.unit_id})))
    db.commit()
    return {"status": "alerted", "notify_roles": ["ADMIN", "SUPER_ADMIN"]}
