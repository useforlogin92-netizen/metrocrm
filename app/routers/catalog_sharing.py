"""Customer-facing property catalog sharing API and preview UI."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services.catalog_sharing import ContactSelection, build_share_payload

router = APIRouter(prefix="/catalog", tags=["catalog-sharing"])
templates = Jinja2Templates(directory="app/templates")


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


def _require_session(request: Request) -> JSONResponse | None:
    if not request.session.get("user_id"):
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    return None


@router.get("/share", response_class=HTMLResponse)
def share_catalog_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the explicit field/media/contact selection screen for staff."""
    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("catalog_share.html", {"request": request})


@router.post("/preview")
def preview_catalog_share(http_request: Request, request: CatalogShareRequest) -> dict[str, Any] | JSONResponse:
    """Preview exactly what would be shared, after authentication and sanitization."""
    auth_error = _require_session(http_request)
    if auth_error:
        return auth_error
    return _payload(request)


@router.post("/share")
def share_catalog(http_request: Request, request: CatalogShareRequest) -> dict[str, Any] | JSONResponse:
    """Return the sanitized share payload for the future delivery provider."""
    auth_error = _require_session(http_request)
    if auth_error:
        return auth_error
    return {"status": "READY", "catalog": _payload(request)}
