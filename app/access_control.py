from __future__ import annotations

from collections.abc import Mapping

from app.permissions import FieldVisibility, Role, SENSITIVE_FIELDS


def mask_phone(value: str | None) -> str | None:
    """Return a privacy-preserving phone representation without exposing the full number."""
    if not value:
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) <= 4:
        return "X" * len(digits)
    if len(digits) <= 6:
        return digits[:2] + "X" * (len(digits) - 2)
    return digits[:2] + "X" * (len(digits) - 4) + digits[-2:]


def mask_email(value: str | None) -> str | None:
    """Keep the first character and use a fixed six-character mask."""
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if not local:
        return "X@" + domain
    return local[:1] + "XXXXXX@" + domain


def visibility_for_field(
    role: Role,
    field: str,
    overrides: Mapping[str, str] | None = None,
) -> FieldVisibility:
    """Resolve Super Admin policy -> role default -> user field override."""
    default = FieldVisibility.VIEW if role in {Role.SUPER_ADMIN, Role.ADMIN, Role.MANAGER} else (
        FieldVisibility.MASKED if field in SENSITIVE_FIELDS else FieldVisibility.VIEW
    )
    raw = (overrides or {}).get(field)
    if raw:
        try:
            return FieldVisibility(raw.upper())
        except ValueError:
            pass
    return default


def visible_value(
    role: Role,
    field: str,
    value: object,
    overrides: Mapping[str, str] | None = None,
) -> object:
    """Apply field-level visibility at the service/API serialization boundary."""
    visibility = visibility_for_field(role, field, overrides)
    if visibility == FieldVisibility.HIDDEN:
        return None
    if visibility == FieldVisibility.MASKED:
        if field in {"mobile", "alternate_mobile"}:
            return mask_phone(str(value) if value is not None else None)
        if field == "email":
            return mask_email(str(value) if value is not None else None)
        return "••••••"
    return value


def sanitize_record(
    role: Role,
    record: Mapping[str, object],
    overrides: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return only values the caller is authorized to receive."""
    return {
        field: visible_value(role, field, value, overrides)
        for field, value in record.items()
        if visibility_for_field(role, field, overrides) != FieldVisibility.HIDDEN
    }
