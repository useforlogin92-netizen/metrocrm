"""Durable, idempotent delivery state for staff follow-up/site-visit reminders."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (UniqueConstraint("reminder_key", name="uq_reminder_delivery_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recipient_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now, index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now, onupdate=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
