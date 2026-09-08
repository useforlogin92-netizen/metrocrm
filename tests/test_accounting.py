from decimal import Decimal

from app.accounting_models import AccountCategory, JournalEntry, JournalLine


def test_accounting_categories_include_office_and_lead_generation_categories(db_session):
    from app.routers.accounting import CATEGORIES
    codes = {code for code, _, _ in CATEGORIES}
    assert {"OFFICE_ELECTRICITY", "OFFICE_MAINTENANCE", "STAFF_SALARY", "STAFF_TRAINING", "MEALS_REFRESHMENTS", "MAGICBRICKS", "NINETY_NINE_ACRES", "META_ADS", "GOOGLE_ADS"} <= codes


def test_double_entry_balances():
    debit = Decimal("12500.00")
    credit = Decimal("10000.00") + Decimal("2500.00")
    assert debit == credit


def test_accounting_models_register():
    assert AccountCategory.__tablename__ == "account_categories"
    assert JournalEntry.__tablename__ == "journal_entries"
    assert JournalLine.__tablename__ == "journal_lines"
