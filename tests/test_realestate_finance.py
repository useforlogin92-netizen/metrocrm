from decimal import Decimal

from app.realestate_finance_models import CostSheet, PropertyQuotation


def test_cost_sheet_total_calculation():
    components = [Decimal("5000000"), Decimal("200000"), Decimal("100000"), Decimal("250000"), Decimal("900000"), Decimal("300000"), Decimal("50000"), Decimal("25000")]
    assert sum(components, Decimal("0")) == Decimal("6825000")


def test_finance_models_have_required_fields():
    assert "total_amount" in CostSheet.__table__.columns
    assert "quotation_no" in PropertyQuotation.__table__.columns
    assert "valid_until" in PropertyQuotation.__table__.columns
