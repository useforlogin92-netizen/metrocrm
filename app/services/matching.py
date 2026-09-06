"""Deterministic customer/property matching helpers.

Supports multiple locations, Mumbai station-to-station ranges, East/West/Both
side filtering, budget/configuration filters and possession flexibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from app.location_catalog import location_priority, mumbai_station_range_matches


@dataclass(slots=True)
class MatchCandidate:
    property_id: int | str
    score: float
    reasons: list[str] = field(default_factory=list)
    location_level: str | None = None
    regional_priority: int = 0
    location_category: str = "Other"


LOCATION_WEIGHT = 30.0
BUDGET_WEIGHT = 25.0
BHK_WEIGHT = 15.0
PROPERTY_TYPE_WEIGHT = 10.0
AREA_WEIGHT = 10.0
POSSESSION_WEIGHT = 10.0


def _normalise(value: object) -> str:
    return str(value or "").strip().casefold()


def _contains_any(value: str, choices: Iterable[str]) -> bool:
    text = _normalise(value)
    return any(_normalise(choice) and _normalise(choice) in text for choice in choices)


def _values(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, (list, tuple, set, frozenset)) else [value]


def _location_component(customer: dict, property_: dict) -> tuple[float, str | None]:
    customer_pins = customer.get("pincodes") or customer.get("preferred_pincodes") or []
    if isinstance(customer_pins, str):
        customer_pins = [customer_pins]
    property_pin = property_.get("pincode")
    if property_pin and any(_normalise(property_pin) == _normalise(pin) for pin in customer_pins):
        return LOCATION_WEIGHT, "pincode"

    # Mumbai caller workflow: From station -> To station + East/West/Both.
    if _normalise(customer.get("city")) == "mumbai" or customer.get("mumbai_station_from") or customer.get("mumbai_station_to"):
        from_station = customer.get("mumbai_station_from")
        to_station = customer.get("mumbai_station_to")
        if from_station or to_station:
            if mumbai_station_range_matches(
                property_station=property_.get("station") or property_.get("railway_station"),
                from_station=from_station,
                to_station=to_station,
                side=customer.get("mumbai_side", "Both"),
                property_side=property_.get("side") or property_.get("location_side") or "Both",
            ):
                return LOCATION_WEIGHT, "mumbai_station_range"
            return 0.0, None

    for level, customer_key, property_key, points in (
        ("locality", "locality", "locality", LOCATION_WEIGHT),
        ("city", "city", "city", LOCATION_WEIGHT * 0.85),
        ("district", "district", "district", LOCATION_WEIGHT * 0.70),
        ("state", "state", "state", LOCATION_WEIGHT * 0.50),
    ):
        wanted = customer.get(customer_key)
        actual = property_.get(property_key)
        if wanted and actual and _contains_any(actual, [str(item) for item in _values(wanted)]):
            return points, level

    locations = customer.get("preferred_locations") or customer.get("locations") or []
    property_location = property_.get("location") or property_.get("locality") or ""
    if locations and _contains_any(property_location, [str(item) for item in _values(locations)]):
        return LOCATION_WEIGHT, "location"
    return 0.0, None


def location_matches(customer: dict, property_: dict) -> bool:
    """Return whether a property satisfies an explicitly requested location filter."""
    has_location_filter = bool(
        customer.get("mumbai_station_from")
        or customer.get("mumbai_station_to")
        or customer.get("preferred_locations")
        or customer.get("locations")
        or customer.get("locality")
        or customer.get("pincodes")
        or customer.get("preferred_pincodes")
    )
    if not has_location_filter:
        return True
    score, _ = _location_component(customer, property_)
    return score > 0


def _possession_matches(customer: dict, property_: dict) -> bool:
    """Match status and/or a possession deadline without confusing RERA and builder dates."""
    statuses = {_normalise(item) for item in _values(customer.get("construction_statuses") or customer.get("construction_status"))}
    property_status = _normalise(property_.get("construction_status") or property_.get("possession"))
    if statuses and property_status not in statuses:
        return False

    requirement = customer.get("possession_by") or customer.get("possession_requirement")
    if requirement is None or requirement == "":
        return bool(statuses and property_status in statuses)

    property_date = property_.get("rera_possession_date") or property_.get("possession_date") or property_.get("possession")
    if property_date is None:
        return False
    try:
        required_year = int(requirement)
    except (TypeError, ValueError):
        return _normalise(requirement) == _normalise(property_date)

    if isinstance(property_date, date):
        property_year = property_date.year
    else:
        text = str(property_date).strip()
        try:
            property_year = int(text[:4])
        except (TypeError, ValueError):
            return False
    return property_year <= required_year


def _configuration_matches(requested: object, actual: object) -> bool:
    """Support one or many BHK/Jodi values while preserving exact configurations."""
    wanted = {_normalise(item) for item in _values(requested) if _normalise(item)}
    actual_value = _normalise(actual)
    if not wanted or not actual_value:
        return False
    actual_variants = {actual_value, actual_value.removeprefix("jodi ")}
    return bool(wanted & actual_variants)


def score_match(customer: dict, property_: dict) -> MatchCandidate:
    """Score one property against a customer requirement on a 0-100 scale."""
    score = 0.0
    reasons: list[str] = []
    location_score, location_level = _location_component(customer, property_)
    if location_score:
        score += location_score
        reasons.append(f"location:{location_level}")

    budget_min = customer.get("budget_min")
    budget_max = customer.get("budget_max")
    price = property_.get("price")
    if price is not None and (budget_min is not None or budget_max is not None):
        lower_ok = budget_min is None or float(price) >= float(budget_min)
        upper_ok = budget_max is None or float(price) <= float(budget_max)
        if lower_ok and upper_ok:
            score += BUDGET_WEIGHT
            reasons.append("budget")

    requested_bhk = customer.get("bhk") or customer.get("bhks") or customer.get("configurations")
    property_bhk = property_.get("bhk") or property_.get("configuration")
    if _configuration_matches(requested_bhk, property_bhk):
        score += BHK_WEIGHT
        reasons.append("bhk")

    requested_type = customer.get("property_type")
    property_type = property_.get("property_type")
    if requested_type and property_type and _normalise(requested_type) == _normalise(property_type):
        score += PROPERTY_TYPE_WEIGHT
        reasons.append("property_type")

    area_min = customer.get("carpet_area_min")
    area_max = customer.get("carpet_area_max")
    area = property_.get("carpet_area")
    if area is not None and (area_min is not None or area_max is not None):
        lower_ok = area_min is None or float(area) >= float(area_min)
        upper_ok = area_max is None or float(area) <= float(area_max)
        if lower_ok and upper_ok:
            score += AREA_WEIGHT
            reasons.append("area")

    if _possession_matches(customer, property_):
        score += POSSESSION_WEIGHT
        reasons.append("possession")

    has_location_filter = bool(
        customer.get("mumbai_station_from")
        or customer.get("mumbai_station_to")
        or customer.get("preferred_locations")
        or customer.get("locations")
        or customer.get("locality")
        or customer.get("pincodes")
        or customer.get("preferred_pincodes")
    )
    location_category = "Selected Location" if location_score else ("Other" if has_location_filter else "All")

    return MatchCandidate(
        property_id=property_.get("id", ""), score=min(score, 100.0), reasons=reasons,
        location_level=location_level,
        regional_priority=location_priority(city=property_.get("city"), district=property_.get("district"), state=property_.get("state")),
        location_category=location_category,
    )


def rank_properties(customer: dict, properties: Iterable[dict], minimum_score: float = 0.0) -> list[MatchCandidate]:
    """Return all matching properties ranked by score and regional priority."""
    candidates = [score_match(customer, item) for item in properties]
    return sorted((item for item in candidates if item.score >= minimum_score), key=lambda item: (-item.score, -item.regional_priority, str(item.property_id)))
