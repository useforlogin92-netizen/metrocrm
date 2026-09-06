"""Deterministic customer/property matching helpers.

The service is intentionally framework-agnostic so the API layer can reuse the
same scoring rules and tests can exercise them without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(slots=True)
class MatchCandidate:
    property_id: int | str
    score: float
    reasons: list[str] = field(default_factory=list)


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


def score_match(customer: dict, property_: dict) -> MatchCandidate:
    """Score one property against a customer requirement on a 0-100 scale."""
    score = 0.0
    reasons: list[str] = []

    locations = customer.get("preferred_locations") or customer.get("locations") or []
    if isinstance(locations, str):
        locations = [locations]
    property_location = property_.get("location") or property_.get("locality") or ""
    if locations and _contains_any(property_location, locations):
        score += LOCATION_WEIGHT
        reasons.append("location")

    budget_min = customer.get("budget_min")
    budget_max = customer.get("budget_max")
    price = property_.get("price")
    if price is not None and (budget_min is not None or budget_max is not None):
        lower_ok = budget_min is None or float(price) >= float(budget_min)
        upper_ok = budget_max is None or float(price) <= float(budget_max)
        if lower_ok and upper_ok:
            score += BUDGET_WEIGHT
            reasons.append("budget")

    requested_bhk = customer.get("bhk")
    property_bhk = property_.get("bhk")
    if requested_bhk and property_bhk:
        if _normalise(requested_bhk) == _normalise(property_bhk):
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

    possession = customer.get("possession_requirement")
    property_possession = property_.get("possession")
    if possession and property_possession and _normalise(possession) == _normalise(property_possession):
        score += POSSESSION_WEIGHT
        reasons.append("possession")

    return MatchCandidate(property_id=property_.get("id", ""), score=min(score, 100.0), reasons=reasons)


def rank_properties(customer: dict, properties: Iterable[dict], minimum_score: float = 0.0) -> list[MatchCandidate]:
    """Return matching properties ranked highest score first."""
    candidates = [score_match(customer, item) for item in properties]
    return sorted(
        (item for item in candidates if item.score >= minimum_score),
        key=lambda item: (-item.score, str(item.property_id)),
    )
