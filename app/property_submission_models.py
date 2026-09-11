from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
