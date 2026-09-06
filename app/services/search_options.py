"""Caller-friendly search option catalog for customer-to-property matching."""

from __future__ import annotations

from datetime import date

BHK_OPTIONS: tuple[str, ...] = ("1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "More than 5 BHK")

# Jodi means combined configurations such as 2+1 or 2+2.
JODI_OPTIONS: tuple[str, ...] = (
    "1+1", "1+2", "1+3", "1+4", "1+5",
    "2+1", "2+2", "2+3", "2+4", "2+5",
    "3+1", "3+2", "3+3", "3+4", "3+5",
    "4+1", "4+2", "4+3", "4+4", "4+5",
    "5+1", "5+2", "5+3", "5+4", "5+5",
)

CONFIGURATION_OPTIONS: tuple[str, ...] = BHK_OPTIONS + tuple(f"Jodi {item}" for item in JODI_OPTIONS)

CONSTRUCTION_STATUS_OPTIONS: tuple[str, ...] = (
    "Ready to Move",
    "Under Construction",
    "Upcoming",
    "Sold Out",
    "Other",
)

POSSESSION_YEARS: tuple[int, ...] = tuple(range(date.today().year, 2051))


def search_option_catalog() -> dict[str, tuple[object, ...]]:
    """Return stable UI/API options; possession is maintained year-wise through 2050."""
    return {
        "bhk": BHK_OPTIONS,
        "jodi": JODI_OPTIONS,
        "configuration": CONFIGURATION_OPTIONS,
        "construction_status": CONSTRUCTION_STATUS_OPTIONS,
        "possession_year": POSSESSION_YEARS,
    }
