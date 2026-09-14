from decimal import Decimal

from app.services.property_pricing import (
    calculate_rate_per_sqft,
    calculate_total_price,
    format_property_value,
    format_rate_per_sqft,
    parse_money,
    pricing_pair,
)


def test_property_value_uses_lakh_below_one_crore():
    assert format_property_value(8_000_000) == "80 lakh"
    assert format_property_value("95 lakh") == "95 lakh"
    assert format_property_value("99.5 lakh") == "99.5 lakh"


def test_property_value_uses_crore_at_or_above_one_crore():
    assert format_property_value(10_000_000) == "1.00 Cr"
    assert format_property_value(11_000_000) == "1.10 Cr"
    assert format_property_value(28_300_000) == "2.83 Cr"
    assert format_property_value("2.10 Cr") == "2.10 Cr"


def test_money_parser_understands_lakh_and_crore():
    assert parse_money("80 lakh") == Decimal("8000000")
    assert parse_money("1.10 Cr") == Decimal("11000000")
    assert parse_money("₹12,50,000") == Decimal("1250000")


def test_bidirectional_sqft_calculation():
    assert calculate_total_price("1000", "12000") == Decimal("12000000")
    assert calculate_rate_per_sqft("1,000", "1.20 Cr") == Decimal("12000")
    rate, total = pricing_pair("1000", total_price="1.2 Cr", source="total")
    assert rate == Decimal("12000")
    assert total == Decimal("12000000")
    rate, total = pricing_pair("1000", rate_per_sqft="12000", source="rate")
    assert rate == Decimal("12000")
    assert total == Decimal("12000000")


def test_rate_display_is_rupees_per_square_foot():
    assert format_rate_per_sqft(12000) == "₹12,000/sq.ft."
