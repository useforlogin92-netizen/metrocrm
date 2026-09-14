from datetime import datetime, timezone
import json

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.services.property_pricing import pricing_pair


class PropertySubmission(Base):
    __tablename__ = "property_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_name: Mapped[str] = mapped_column(String(200))
    recipient_mobile: Mapped[str | None] = mapped_column(String(30))
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="OPEN", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    admin_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    super_admin_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    super_admin_approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


@event.listens_for(PropertySubmission, "before_update")
def _preserve_payload_when_status_does_not_change(mapper, connection, target: PropertySubmission) -> None:
    """Preserve failed-form payloads, while normalizing a real submission's pricing."""
    state = inspect(target)
    payload_history = state.attrs.payload_json.history
    status_history = state.attrs.status.history
    if not payload_history.has_changes():
        return
    if not status_history.has_changes():
        if payload_history.deleted:
            target.payload_json = payload_history.deleted[0]
        elif payload_history.unchanged:
            target.payload_json = payload_history.unchanged[0]
        return

    try:
        payload = json.loads(target.payload_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return
    details = payload.get("configuration_details")
    if not isinstance(details, list):
        return
    normalized = []
    for item in details:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        source = str(item.get("pricing_source") or "rate").lower()
        rate, total = pricing_pair(item.get("carpet_area"), item.get("rate_per_sqft"), item.get("bundle_price"), source)
        if rate is not None:
            item["rate_per_sqft"] = format(rate, ".2f").rstrip("0").rstrip(".")
        if total is not None:
            item["bundle_price"] = format(total, ".2f").rstrip("0").rstrip(".")
        item["pricing_source"] = source if source in {"rate", "total"} else "rate"
        normalized.append(item)
    payload["configuration_details"] = normalized
    if normalized:
        first = normalized[0]
        payload["starting_price"] = first.get("bundle_price", payload.get("starting_price", ""))
        payload["rate_per_sqft"] = first.get("rate_per_sqft", payload.get("rate_per_sqft", ""))
        payload["bundle_price"] = first.get("bundle_price", payload.get("bundle_price", ""))
    target.payload_json = json.dumps(payload, ensure_ascii=False)
