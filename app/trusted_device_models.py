"""Trusted device records for privileged Super Admin sessions."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_name: Mapped[str] = mapped_column(String(120), default="Satyapal Yadav PC")
    public_key_jwk: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_ip: Mapped[str | None] = mapped_column(String(64))
