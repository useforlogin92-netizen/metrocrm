"""Mock-first cloud calling records; no external provider is contacted."""
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CloudCallLog(Base):
    __tablename__ = "cloud_call_logs"
    __table_args__ = (
        CheckConstraint("call_type IN ('inbound', 'outbound')", name="ck_cloud_call_type"),
        CheckConstraint("status IN ('initiated', 'ringing', 'in_progress', 'completed', 'missed', 'failed', 'cancelled')", name="ck_cloud_call_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    agent_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    call_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="initiated", index=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="mock")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now, onupdate=_now)
