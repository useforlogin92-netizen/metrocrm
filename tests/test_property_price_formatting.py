from decimal import Decimal
from app.services.property_pricing import format_property_value, parse_money

def test_crores_are_trimmed_and_rounded():
    assert format_property_value(25_000_000) == "2.5 Cr"
    assert format_property_value(13_000_000) == "1.3 Cr"
    assert format_property_value(10_050_000) == "1.01 Cr"

def test_lakhs_are_formatted_below_one_crore():
    assert format_property_value(9_500_000) == "95 Lakh"
    assert format_property_value(950_000) == "9.5 Lakh"
    assert format_property_value(100_000) == "1 Lakh"

def test_preformatted_values_are_not_multiplied_twice():
    assert format_property_value("95 Lakh") == "95 Lakh"
    assert format_property_value("2.5 Cr") == "2.5 Cr"
    assert parse_money("2.5 Cr") == Decimal("25000000.0")

def test_small_values_keep_indian_grouping():
    assert format_property_value(75_000) == "₹75,000"
