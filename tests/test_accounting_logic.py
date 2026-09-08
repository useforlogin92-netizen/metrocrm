from datetime import datetime
from decimal import Decimal

import pytest

from app.accounting_logic import post_transaction
from app.accounting_models import AccountCategory, AccountingEntry, JournalEntry, JournalLine


def seed_accounts(db):
    from app.routers.accounting import CATEGORIES
    db.add_all(AccountCategory(code=c, name=n, account_type=t, is_system=True) for c, n, t in CATEGORIES)
    db.commit()


def test_expense_posts_balanced_double_entry_with_gst_and_tds(db_session):
    seed_accounts(db_session)
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="META_ADS", description="Meta lead campaign", amount=Decimal("10000"), gst_amount=Decimal("1800"), tds_amount=Decimal("500"), payment_mode="Bank", party_name="Meta")
    db_session.add(entry)
    db_session.flush()
    post_transaction(db_session, entry, user_id=1, entry_no="TXN-001")
    db_session.commit()
    lines = db_session.query(JournalLine).all()
    assert sum(x.debit for x in lines) == sum(x.credit for x in lines) == Decimal("11800")
    assert {x.account_code for x in lines} == {"META_ADS", "INPUT_CGST", "TDS_PAYABLE", "BANK"}


def test_income_posts_balanced_double_entry(db_session):
    seed_accounts(db_session)
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="INCOME", category_code="SALES_REVENUE", description="Brokerage received", amount=Decimal("50000"), gst_amount=Decimal("9000"), payment_mode="Bank")
    db_session.add(entry)
    db_session.flush()
    post_transaction(db_session, entry, user_id=1, entry_no="TXN-002")
    db_session.commit()
    lines = db_session.query(JournalLine).all()
    assert sum(x.debit for x in lines) == sum(x.credit for x in lines) == Decimal("59000")


def test_tds_cannot_exceed_gross_value(db_session):
    seed_accounts(db_session)
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="PROFESSIONAL_FEES", description="Consultancy", amount=Decimal("1000"), gst_amount=Decimal("0"), tds_amount=Decimal("1001"), payment_mode="Bank")
    db_session.add(entry)
    db_session.flush()
    with pytest.raises(ValueError, match="TDS"):
        post_transaction(db_session, entry, user_id=1, entry_no="TXN-003")


def test_duplicate_journal_number_is_rejected(db_session):
    seed_accounts(db_session)
    db_session.add(JournalEntry(entry_no="TXN-004", entry_date=datetime(2026, 9, 8), narration="Existing", created_by_id=1))
    db_session.commit()
    entry = AccountingEntry(entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="OFFICE_RENT", description="Rent", amount=Decimal("1000"), payment_mode="Bank")
    db_session.add(entry)
    db_session.flush()
    with pytest.raises(ValueError, match="Duplicate"):
        post_transaction(db_session, entry, user_id=1, entry_no="TXN-004")
