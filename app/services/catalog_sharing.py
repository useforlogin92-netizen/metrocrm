"""Safe, explicit customer-facing property catalog sharing helpers.

The sharing layer is deliberately selection-driven: no contact is selected by
 default and confidential/internal fields are never customer-facing, even if a
 caller tries to request them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

CONTACT_TYPES = frozenset({"salesperson", "closing_manager", "company", "custom"})
CONTACT_FIELDS = frozenset({"name", "mobile", "whatsapp", "email"})

# These are never allowed into a customer-facing payload.
BLOCKED_FIELDS = frozenset(
    {
        "internal_notes",
        "customer_notes",
        "internal_source",
        "owner_private_contact",
        "developer_internal_contact",
        "broker_internal_details",
        "cp_internal_details",
        "commission_percent",
        "commission_amount",
        "company_margin",
        "salesperson_incentive",
        "internal_negotiation_notes",
        "minimum_acceptable_price",
        "internal_purchase_price",
        "internal_valuation",
        "internal_documents",
    }
)


@dataclass(frozen=True, slots=True)
class ContactSelection:
    """One explicitly selected contact and its individually selected fields."""

    contact_type: str
    fields: frozenset[str] = field(default_factory=frozenset)

    def normalized(self) -> "ContactSelection":
        if self.contact_type not in CONTACT_TYPES:
            return ContactSelection(self.contact_type, frozenset())
        return ContactSelection(
            self.contact_type,
            frozenset(f for f in self.fields if f in CONTACT_FIELDS),
        )


def build_share_payload(
    property_data: Mapping[str, Any],
    *,
    selected_fields: set[str] | frozenset[str] = frozenset(),
    selected_media_ids: set[str] | frozenset[str] = frozenset(),
    media: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
    contacts: Mapping[str, Mapping[str, Any]] | None = None,
    contact_selections: tuple[ContactSelection, ...] = (),
) -> dict[str, Any]:
    """Build the exact customer payload from explicit selections.

    ``preview`` and final sharing should call this same function so the preview
    cannot accidentally expose more data than the actual share operation.
    """
    safe_fields = {
        key: property_data[key]
        for key in selected_fields
        if key in property_data and key not in BLOCKED_FIELDS
    }

    selected_ids = set(selected_media_ids)
    safe_media = [
        dict(item)
        for item in media
        if str(item.get("id")) in selected_ids and not item.get("internal_only", False)
    ]

    safe_contacts: dict[str, dict[str, Any]] = {}
    contacts = contacts or {}
    for selection in contact_selections:
        normalized = selection.normalized()
        if normalized.contact_type not in CONTACT_TYPES:
            continue
        source = contacts.get(normalized.contact_type)
        if not source:
            continue
        chosen = {
            key: source[key]
            for key in normalized.fields
            if key in source and key in CONTACT_FIELDS
        }
        if chosen:
            safe_contacts[normalized.contact_type] = chosen

    return {
        "fields": safe_fields,
        "media": safe_media,
        "contacts": safe_contacts,
    }


def build_share_preview(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Return exactly the same sanitized payload that the share operation uses."""
    return build_share_payload(*args, **kwargs)
