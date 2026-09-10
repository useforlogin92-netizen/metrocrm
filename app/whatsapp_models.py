"""Database model for controlled WhatsApp communication history."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    destination_hash: Mapped[str] = mapped_column(String(64), index=True)
    message_type: Mapped[str] = mapped_column(String(40), default="text")
    template_name: Mapped[str | None] = mapped_column(String(120))
    body_preview: Mapped[str] = mapped_column(String(500), default="")
    property_context_json: Mapped[str] = mapped_column(Text, default="{}")
    provider: Mapped[str] = mapped_column(String(80), default="whatsapp_cloud")
    status: Mapped[str] = mapped_column(String(30), default="TEST")
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
