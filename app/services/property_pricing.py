"""Shared Indian real-estate pricing parsing, calculation and display helpers."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

CRORE = Decimal("10000000")
LAKH = Decimal("100000")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_money(value: Any) -> Decimal | None:
    """Parse rupees, lakh/lac and crore/Cr inputs into rupees."""
    if value is None:
        return None
    text = str(value).strip().lower().replace("₹", "").replace(",", "")
    if not text:
        return None
    text = (
        text.replace("crores", "crore")
        .replace("crs", "cr")
        .replace("lacs", "lakh")
        .replace("lac", "lakh")
    )
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(crore|cr|lakh|lakhs)?", text)
    if not match:
        return None
    number = _decimal(match.group(1))
    if number is None:
        return None
    unit = match.group(2) or ""
    if unit in {"crore", "cr"}:
        return number * CRORE
    if unit in {"lakh", "lakhs"}:
        return number * LAKH
    return number


def _trim(value: Decimal, places: str = "0.01") -> str:
    rounded = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _crore_display(value: Decimal) -> str:
    """Format crores to at most two decimal places, removing trailing zeros."""
    return _trim(value / Decimal("1"), "0.01")


def _indian_integer(value: Decimal) -> str:
    n = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "-" if n < 0 else ""
    digits = str(abs(n))
    if len(digits) <= 3:
        return sign + digits
    last = digits[-3:]
    prefix = digits[:-3]
    groups = []
    while prefix:
        groups.append(prefix[-2:])
        prefix = prefix[:-2]
    return sign + ",".join(reversed(groups)) + "," + last


def format_property_value(value: Any) -> str:
    """Format rupee amounts in readable Indian units: Lakh below 1 Cr, Cr otherwise."""
    amount = parse_money(value)
    if amount is None:
        return "Price on request"
    if amount >= CRORE:
        return f"{_crore_display(amount / CRORE)} Cr"
    if amount >= LAKH:
        return f"{_trim(amount / LAKH)} Lakh"
    if amount <= -CRORE:
        return f"{_crore_display(abs(amount) / CRORE)} Cr"
    if amount <= -LAKH:
        return f"{_trim(abs(amount) / LAKH)} Lakh"
    return f"₹{_indian_integer(amount)}"


def format_rate_per_sqft(value: Any) -> str:
    amount = _decimal(value)
    if amount is None:
        return ""
    return f"₹{_indian_integer(amount)}/sq.ft."


def calculate_total_price(carpet_area: Any, rate_per_sqft: Any) -> Decimal | None:
    area = _decimal(carpet_area)
    rate = _decimal(rate_per_sqft)
    if area is None or rate is None or area <= 0 or rate < 0:
        return None
    return area * rate


def calculate_rate_per_sqft(carpet_area: Any, total_price: Any) -> Decimal | None:
    area = _decimal(carpet_area)
    total = parse_money(total_price)
    if area is None or total is None or area <= 0 or total < 0:
        return None
    return total / area


def pricing_pair(
    carpet_area: Any,
    rate_per_sqft: Any = None,
    total_price: Any = None,
    source: str = "rate",
) -> tuple[Decimal | None, Decimal | None]:
    """Return normalized (rate/sq.ft., total price) using the last edited source."""
    if source == "total":
        total = parse_money(total_price)
        rate = calculate_rate_per_sqft(carpet_area, total)
        return rate, total
    rate = _decimal(rate_per_sqft)
    total = calculate_total_price(carpet_area, rate)
    return rate, total
