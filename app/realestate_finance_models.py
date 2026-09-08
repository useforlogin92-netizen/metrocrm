from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CostSheet(Base):
    __tablename__ = "cost_sheets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    plc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    floor_rise: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    parking: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    gst: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    stamp_duty: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    registration: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    other_charges: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class PropertyQuotation(Base):
    __tablename__ = "property_quotations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    cost_sheet_id: Mapped[int | None] = mapped_column(ForeignKey("cost_sheets.id"))
    quotation_no: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    valid_until: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
