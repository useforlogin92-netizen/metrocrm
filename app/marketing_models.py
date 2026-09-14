from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    channel: Mapped[str] = mapped_column(String(40), index=True)
    objective: Mapped[str] = mapped_column(String(80), default="LEAD_GENERATION")
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    landing_token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    landing_title: Mapped[str | None] = mapped_column(String(250))
    landing_subtitle: Mapped[str | None] = mapped_column(String(500))
    catalog_share_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_shares.id"), index=True)
    utm_source: Mapped[str | None] = mapped_column(String(100))
    utm_medium: Mapped[str | None] = mapped_column(String(100))
    utm_campaign: Mapped[str | None] = mapped_column(String(150))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


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
