from datetime import datetime
from decimal import Decimal

from app.accounting_logic import post_transaction
from app.accounting_models import AccountCategory, AccountingEntry, JournalLine
from app.models import User


def seed_accounts(db):
    from app.routers.accounting import CATEGORIES
    db.add(User(username="accounting-credit-test", password_hash="test", role="ADMIN", is_active=True, is_approved=True))
    db.flush()
    db.add_all(AccountCategory(code=c, name=n, account_type=t, is_system=True) for c, n, t in CATEGORIES)
    db.commit()
    return db.query(User).filter_by(username="accounting-credit-test").one().id


def test_credit_expense_posts_to_vendor_payable(db_session):
    user_id = seed_accounts(db_session)
    entry = AccountingEntry(
        entry_date=datetime(2026, 9, 8), entry_type="EXPENSE", category_code="MAGICBRICKS",
        description="Portal expense on credit", amount=Decimal("12000"), payment_mode="Credit",
        party_name="MagicBricks", created_by_id=user_id,
    )
    db_session.add(entry)
    db_session.flush()
    post_transaction(db_session, entry, user_id=user_id, entry_no="CREDIT-EXP-001")
    db_session.commit()
    lines = db_session.query(JournalLine).all()
    assert sum(x.debit for x in lines) == sum(x.credit for x in lines) == Decimal("12000")
    assert {x.account_code for x in lines} == {"MAGICBRICKS", "VENDOR_PAYABLE"}


def test_credit_income_posts_to_customer_receivable(db_session):
    user_id = seed_accounts(db_session)
    entry = AccountingEntry(
        entry_date=datetime(2026, 9, 8), entry_type="INCOME", category_code="SALES_REVENUE",
        description="Brokerage billed on credit", amount=Decimal("25000"), payment_mode="Credit",
        party_name="Client", created_by_id=user_id,
    )
    db_session.add(entry)
    db_session.flush()
    post_transaction(db_session, entry, user_id=user_id, entry_no="CREDIT-IN-001")
    db_session.commit()
    lines = db_session.query(JournalLine).all()
    assert sum(x.debit for x in lines) == sum(x.credit for x in lines) == Decimal("25000")
    assert {x.account_code for x in lines} == {"CUSTOMER_RECEIVABLE", "SALES_REVENUE"}
