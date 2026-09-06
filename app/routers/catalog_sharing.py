"""Customer-facing property catalog sharing API helpers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.catalog_sharing import ContactSelection, build_share_payload

router = APIRouter(prefix="/catalog", tags=["catalog-sharing"])


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


@router.post("/preview")
def preview_catalog_share(request: CatalogShareRequest) -> dict[str, Any]:
    """Preview exactly what would be shared, after server-side sanitization."""
    return _payload(request)


@router.post("/share")
def share_catalog(request: CatalogShareRequest) -> dict[str, Any]:
    """Return the sanitized share payload for the future delivery provider."""
    return {"status": "READY", "catalog": _payload(request)}
