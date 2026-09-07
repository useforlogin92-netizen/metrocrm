"""Database models for external lead/communication integrations and property-visit alerts."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(30), default="webhook")
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class LeadIntegrationEvent(Base):
    __tablename__ = "lead_integration_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    external_lead_id: Mapped[str | None] = mapped_column(String(255), index=True)
    lead_id: Mapped[int | None] = mapped_column(Integer, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PropertyVisitAlert(Base):
    __tablename__ = "property_visit_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    unit_id: Mapped[int | None] = mapped_column(Integer, index=True)
    lead_id: Mapped[int | None] = mapped_column(Integer, index=True)
    visitor_ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    page_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
