from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SiteVisitReview(Base):
    """Post-visit details kept separately to avoid altering existing live SiteVisit columns."""
    __tablename__ = "site_visit_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("site_visits.id"), unique=True, index=True)
    batch_key: Mapped[str] = mapped_column(String(36), index=True)
    called_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sm_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    customer_feedback: Mapped[str | None] = mapped_column(Text)
    interest_level: Mapped[str | None] = mapped_column(String(30))
    deal_status: Mapped[str] = mapped_column(String(40), default="FOLLOW_UP_REQUIRED")
    quoted_price: Mapped[str | None] = mapped_column(String(100))
    customer_objections: Mapped[str | None] = mapped_column(Text)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    followup_id: Mapped[int | None] = mapped_column(ForeignKey("followups.id"), nullable=True)
    next_followup_plan: Mapped[str | None] = mapped_column(Text)
    next_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    other_project_required: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DeveloperSalesContact(Base):
    """Developer-side sales manager contact entered for a specific site visit."""
    __tablename__ = "site_visit_developer_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("site_visits.id"), unique=True, index=True)
    sm_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sm_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SiteVisitCheckIn(Base):
    """Explicit, one-time GPS check-in record for a scheduled site visit."""
    __tablename__ = "site_visit_checkins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("site_visits.id"), unique=True, index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    latitude: Mapped[float] = mapped_column(__import__("sqlalchemy").Numeric(10, 7))
    longitude: Mapped[float] = mapped_column(__import__("sqlalchemy").Numeric(10, 7))
    accuracy_m: Mapped[float | None] = mapped_column(__import__("sqlalchemy").Numeric(8, 2), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
