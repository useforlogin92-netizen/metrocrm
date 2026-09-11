from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
    """Do not replace the last good payload during a failed validation retry.

    The public submission handler stores the form state before returning a 422
    validation response. A real correction/resubmission changes the status in
    the same transaction, so that update is intentionally allowed. If only the
    payload changes while the workflow status stays OPEN/CORRECTION_REQUESTED,
    keep the last committed property payload intact.
    """
    state = inspect(target)
    payload_history = state.attrs.payload_json.history
    status_history = state.attrs.status.history
    if payload_history.has_changes() and not status_history.has_changes():
        if payload_history.deleted:
            target.payload_json = payload_history.deleted[0]
        elif payload_history.unchanged:
            target.payload_json = payload_history.unchanged[0]
