"""Caller-friendly property search and matching API helpers."""
from __future__ import annotations

from typing import Any, Iterable

from app.services.matching import MatchCandidate, location_matches, rank_properties

BUDGET_SLABS = [("Below 1 Cr", None, 10_000_000), ("1–2 Cr", 10_000_000, 20_000_000), ("2–3 Cr", 20_000_000, 30_000_000), ("3–4 Cr", 30_000_000, 40_000_000), ("4–5 Cr", 40_000_000, 50_000_000), ("5–6 Cr", 50_000_000, 60_000_000), ("6–7 Cr", 60_000_000, 70_000_000), ("7–8 Cr", 70_000_000, 80_000_000), ("8–9 Cr", 80_000_000, 90_000_000), ("9–10 Cr", 90_000_000, 100_000_000), ("10–12 Cr", 100_000_000, 120_000_000), ("12–15 Cr", 120_000_000, 150_000_000), ("15–20 Cr", 150_000_000, 200_000_000), ("Above 20 Cr", 200_000_000, None)]
BHK_OPTIONS = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "More"]
JODI_OPTIONS = ["2+1", "2+2", "3+1", "3+2", "3+3", "4+2", "4+3", "4+4"]
CONSTRUCTION_OPTIONS = ["Ready to Move", "Under Construction", "Upcoming", "Sold Out"]
SIDE_OPTIONS = ["East", "West", "Both"]


def filter_and_rank_properties(filters: dict[str, Any], properties: Iterable[dict[str, Any]]) -> list[MatchCandidate]:
    candidates = list(properties)
    construction = filters.get("construction_statuses") or filters.get("construction_status")
    if construction:
        wanted = {str(v).strip().casefold() for v in (construction if isinstance(construction, (list, tuple, set)) else [construction])}
        candidates = [p for p in candidates if str(p.get("construction_status") or p.get("possession") or "").strip().casefold() in wanted]
    if filters.get("city"):
        city = str(filters["city"]).strip().casefold()
        candidates = [p for p in candidates if str(p.get("city") or "").strip().casefold() == city]

    # Location is a hard caller filter: an unrelated property must never appear
    # merely because it matches budget/BHK and reaches the minimum score.
    if any(filters.get(key) for key in ("mumbai_station_from", "mumbai_station_to", "preferred_locations", "locations", "locality", "pincodes", "preferred_pincodes")):
        candidates = [p for p in candidates if location_matches(filters, p)]

    return rank_properties(filters, candidates, minimum_score=0.0)


def build_search_summary(filters: dict[str, Any], result_count: int) -> str:
    parts = []
    if filters.get("city"): parts.append(str(filters["city"]))
    if filters.get("mumbai_station_from") or filters.get("mumbai_station_to"):
        parts.append(f"{filters.get('mumbai_station_from') or 'Any'} → {filters.get('mumbai_station_to') or 'Any'}")
        parts.append(str(filters.get("mumbai_side", "Both")))
    if filters.get("bhk"): parts.append(", ".join(map(str, filters["bhk"] if isinstance(filters["bhk"], list) else [filters["bhk"]])))
    if filters.get("construction_statuses"): parts.append(", ".join(map(str, filters["construction_statuses"])))
    if filters.get("possession_by"): parts.append(f"Possession ≤ {filters['possession_by']}")
    return f"{result_count} matching properties" + (" — " + " | ".join(parts) if parts else "")
