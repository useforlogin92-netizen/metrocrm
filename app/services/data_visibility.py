from __future__ import annotations

import json
import re
from collections.abc import Mapping

from app.permissions import FieldVisibility

DEFAULT_SENSITIVE_VISIBILITY: dict[str, str] = {
    "mobile": FieldVisibility.MASKED.value,
    "alternate_mobile": FieldVisibility.MASKED.value,
    "email": FieldVisibility.MASKED.value,
    "address": FieldVisibility.HIDDEN.value,
    "budget_min": FieldVisibility.HIDDEN.value,
    "budget_max": FieldVisibility.HIDDEN.value,
    "requirement": FieldVisibility.HIDDEN.value,
    "internal_notes": FieldVisibility.HIDDEN.value,
    "booking_amount": FieldVisibility.HIDDEN.value,
    "sale_value": FieldVisibility.HIDDEN.value,
    "commission_amount": FieldVisibility.HIDDEN.value,
    "documents": FieldVisibility.HIDDEN.value,
}


def parse_json_map(value: str | Mapping[str, object] | None) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def mask_mobile(value: object) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 6:
        return "X" * len(digits) if digits else None
    return f"{digits[:2]}{'X' * (len(digits) - 4)}{digits[-2:]}"


def mask_email(value: object) -> str | None:
    if value is None:
        return None
    email = str(value).strip()
    if "@" not in email:
        return "X" * min(len(email), 6) if email else None
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}{'X' * max(1, len(local) - 1)}@{domain}"


def visible_value(field: str, value: object, mode: str) -> object:
    normalized = str(mode or FieldVisibility.VIEW.value).upper()
    if normalized == FieldVisibility.HIDDEN.value:
        return None
    if normalized != FieldVisibility.MASKED.value:
        return value
    if field in {"mobile", "alternate_mobile"}:
        return mask_mobile(value)
    if field == "email":
        return mask_email(value)
    if value is None:
        return None
    return "••••••"


def sanitize_record(record: Mapping[str, object], visibility: str | Mapping[str, object] | None = None) -> dict[str, object]:
    """Apply field visibility at the data boundary; never rely on UI hiding."""
    overrides = parse_json_map(visibility)
    result: dict[str, object] = {}
    for field, value in record.items():
        mode = overrides.get(field, DEFAULT_SENSITIVE_VISIBILITY.get(field, FieldVisibility.VIEW.value))
        result[field] = visible_value(field, value, str(mode))
    return result
