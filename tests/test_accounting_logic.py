from datetime import datetime
from decimal import Decimal

import pytest

from app.accounting_logic import post_transaction
from app.accounting_models import AccountCategory, AccountingEntry, AccountingPeriod, JournalEntry, JournalLine
from app.models import User


def seed_accounts(db):
    from app.routers.accounting import CATEGORIES
    db.add(User(username="accounting-test", password_hash="test", role="ADMIN", is_active=True, is_approved=True))
    db.flush()
    db.add_all(AccountCategory(code=c, name=n, account_type=t, is_system=True) for c, n, t in CATEGORIES)
    db.commit()
    return db.query(User).filter_by(username="accounting-test").one().id


def test_expense_posts_balanced_double_entry_with_gst_and_tds(db_session):
    user_id = seed_accounts(db_session)
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="META_ADS", description="Meta lead campaign", amount=Decimal("10000"), gst_amount=Decimal("1800"), tds_amount=Decimal("500"), payment_mode="Bank", party_name="Meta", created_by_id=user_id)
    db_session.add(entry)
    db_session.flush()
    post_transaction(db_session, entry, user_id=user_id, entry_no="TXN-001")
    db_session.commit()
    lines = db_session.query(JournalLine).all()
    assert sum(x.debit for x in lines) == sum(x.credit for x in lines) == Decimal("11800")
    assert {x.account_code for x in lines} == {"META_ADS", "INPUT_CGST", "TDS_PAYABLE", "BANK"}


def test_income_posts_balanced_double_entry(db_session):
    user_id = seed_accounts(db_session)
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="INCOME", category_code="SALES_REVENUE", description="Brokerage received", amount=Decimal("50000"), gst_amount=Decimal("9000"), payment_mode="Bank", created_by_id=user_id)
    db_session.add(entry)
    db_session.flush()
    post_transaction(db_session, entry, user_id=user_id, entry_no="TXN-002")
    db_session.commit()
    lines = db_session.query(JournalLine).all()
    assert sum(x.debit for x in lines) == sum(x.credit for x in lines) == Decimal("59000")


def test_tds_cannot_exceed_gross_value(db_session):
    user_id = seed_accounts(db_session)
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="PROFESSIONAL_FEES", description="Consultancy", amount=Decimal("1000"), gst_amount=Decimal("0"), tds_amount=Decimal("1001"), payment_mode="Bank", created_by_id=user_id)
    db_session.add(entry)
    db_session.flush()
    with pytest.raises(ValueError, match="TDS"):
        post_transaction(db_session, entry, user_id=user_id, entry_no="TXN-003")


def test_duplicate_journal_number_is_rejected(db_session):
    user_id = seed_accounts(db_session)
    db_session.add(JournalEntry(entry_no="TXN-004", entry_date=datetime(2026, 9, 8), narration="Existing", created_by_id=user_id))
    db_session.commit()
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="OFFICE_RENT", description="Rent", amount=Decimal("1000"), payment_mode="Bank", created_by_id=user_id)
    db_session.add(entry)
    db_session.flush()
    with pytest.raises(ValueError, match="Duplicate"):
        post_transaction(db_session, entry, user_id=user_id, entry_no="TXN-004")


def test_closed_accounting_period_is_available_for_route_guard(db_session):
    period = AccountingPeriod(period_name="FY 2025-26", from_date=datetime(2025, 4, 1), to_date=datetime(2026, 3, 31), status="CLOSED")
    db_session.add(period)
    db_session.commit()
    assert db_session.query(AccountingPeriod).filter_by(status="CLOSED").count() == 1
