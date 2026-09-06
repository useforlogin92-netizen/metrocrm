"""Project/property visitor alert primitives."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass(slots=True)
class VisitorEvent:
    project_id: int
    property_id: int | None
    page: str
    occurred_at: datetime
    visitor_key: str
    source: str | None = None


def visitor_key(raw_identifier: str) -> str:
    """Hash a visitor identifier before persistence; do not store raw IPs."""
    return hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()


def within_cooldown(previous: datetime | None, now: datetime, seconds: int = 60) -> bool:
    return bool(previous and now - previous < timedelta(seconds=max(0, seconds)))
