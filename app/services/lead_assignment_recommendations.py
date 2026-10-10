"""Explainable workload-based lead assignment suggestions.

This module recommends an owner but never mutates a lead or approves an assignment.
The caller must enforce authorization and obtain an explicit manager approval.
"""
from __future__ import annotations

from typing import Any, Iterable

ELIGIBLE_ROLES = {"SALES_EXECUTIVE", "TELECALLER"}
CLOSED_STATUSES = {
    "BOOKED", "CLOSED", "LOST", "INVALID", "DUPLICATE",
    "NOT_INTERESTED", "CANCELLED",
}


def recommend_lead_assignees(
    lead: Any,
    candidates: Iterable[Any],
    open_lead_counts: dict[int, int],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Rank active caller candidates by current open-lead workload.

    Inputs may be SQLAlchemy objects or dictionaries. Workload is the only
    default signal because the current User schema does not define reliable
    service-area/language/availability fields. Reasons make the ranking
    explainable and the result is advisory only.
    """
    if limit < 1:
        return []

    def value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    current_owner = value(lead, "assigned_user_id")
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        user_id = value(candidate, "id")
        role = str(value(candidate, "role", "") or "").upper()
        active = bool(value(candidate, "is_active", False))
        if not isinstance(user_id, int) or not active or role not in ELIGIBLE_ROLES:
            continue
        if user_id == current_owner:
            continue

        workload = max(0, int(open_lead_counts.get(user_id, 0)))
        ranked.append({
            "user_id": user_id,
            "username": str(value(candidate, "username", f"Caller {user_id}")),
            "role": role,
            "open_lead_count": workload,
            "score": max(0, 100 - min(workload, 100)),
            "reasons": [
                "Active eligible caller",
                f"{workload} currently open lead(s)",
                "Ranked to balance current workload; manager approval required",
            ],
        })

    ranked.sort(key=lambda item: (item["open_lead_count"], item["username"].casefold(), item["user_id"]))
    return ranked[:limit]
