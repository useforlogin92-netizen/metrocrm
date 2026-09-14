"""Marketing attribution models.

MarketingCampaign is defined in crm_plus_models because it is part of the
existing CRM campaign model. This module re-exports it for the marketing
router/tests and owns the marketing-specific event/visit tables.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.crm_plus_models import MarketingCampaign


class MarketingLeadEvent(Base):
    __tablename__ = "marketing_lead_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("marketing_campaigns.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    source: Mapped[str] = mapped_column(String(60), default="MARKETING")
    medium: Mapped[str | None] = mapped_column(String(100))
    campaign: Mapped[str | None] = mapped_column(String(150))
    content: Mapped[str | None] = mapped_column(String(150))
    term: Mapped[str | None] = mapped_column(String(150))
    click_id: Mapped[str | None] = mapped_column(String(255))
    landing_path: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class MarketingLandingVisit(Base):
    __tablename__ = "marketing_landing_visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("marketing_campaigns.id"), index=True)
    visitor_hash: Mapped[str] = mapped_column(String(64), index=True)
    referrer: Mapped[str | None] = mapped_column(String(1000))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
