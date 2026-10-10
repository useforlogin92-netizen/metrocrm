"""Feature-local logic for MetroCRM user management.

Keep this module free of route registration and global application imports so
user-management filtering and permission validation can be tested in isolation.
"""
from __future__ import annotations

import json
from typing import Iterable

from app.permissions import Access


VALID_PERMISSION_MODULES = {
    "leads", "customers", "properties", "followups", "reports", "users",
    "integrations", "site_visits", "bookings", "accounting", "exports", "audit_logs",
}
VALID_PERMISSION_ACTIONS = {action.value for action in Access}


def filter_user_records(
    users: Iterable[object],
    *,
    query: str = "",
    role: str = "",
    category: str = "",
    team: str = "",
    status: str = "",
    created_from: str = "",
    created_to: str = "",
) -> list[object]:
    """Filter only the user objects passed by the caller's authorization scope."""
    query = query.strip().casefold()
    role = role.strip().upper()
    category = category.strip().casefold()
    team = team.strip().casefold()
    status = status.strip().lower()
    result = []
    for user in users:
        searchable = " ".join(filter(None, [
            user.username, user.email, user.mobile, user.category, user.team,
        ])).casefold()
        if query and query not in searchable:
            continue
        if role and user.role.upper() != role:
            continue
        if category and category not in (user.category or "").casefold():
            continue
        if team and team not in (user.team or "").casefold():
            continue
        if status == "active" and not user.is_active:
            continue
        if status == "disabled" and user.is_active:
            continue
        if status == "pending" and user.is_approved:
            continue
        if status == "approved" and not user.is_approved:
            continue
        created_day = user.created_at.date().isoformat() if user.created_at else ""
        if created_from and (not created_day or created_day < created_from):
            continue
        if created_to and (not created_day or created_day > created_to):
            continue
        result.append(user)
    return result


def parse_permission_overrides(raw: str) -> dict:
    """Validate the allow/deny JSON accepted by user_allows; reject unknown keys."""
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Permission overrides must be valid JSON") from exc
    if not isinstance(value, dict) or set(value) - {"allow", "deny"}:
        raise ValueError("Only allow and deny sections are supported")
    for section in value.values():
        if not isinstance(section, dict):
            raise ValueError("Each permission section must be an object")
        for module, actions in section.items():
            if module not in VALID_PERMISSION_MODULES and module != "*":
                raise ValueError(f"Unknown permission module: {module}")
            if not isinstance(actions, list) or any(
                not isinstance(action, str) or action not in VALID_PERMISSION_ACTIONS
                for action in actions
            ):
                raise ValueError(f"Invalid action list for module: {module}")
    return value
