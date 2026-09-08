from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AccountCategory(Base):
    __tablename__ = "account_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(30))  # INCOME, EXPENSE, ASSET, LIABILITY, EQUITY
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("account_categories.id"))
    is_system: Mapped[bool] = mapped_column(default=True)


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    entry_type: Mapped[str] = mapped_column(String(30), default="EXPENSE", index=True)
    category_code: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    tds_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    payment_mode: Mapped[str | None] = mapped_column(String(30))
    party_name: Mapped[str | None] = mapped_column(String(200))
    invoice_no: Mapped[str | None] = mapped_column(String(100), index=True)
    reference_no: Mapped[str | None] = mapped_column(String(150))
    bank_account: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_name: Mapped[str] = mapped_column(String(100))
    from_date: Mapped[datetime] = mapped_column(DateTime)
    to_date: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
