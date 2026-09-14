"""Caller-friendly property search and matching API helpers."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from app.services.matching import MatchCandidate, mumbai_station_range_matches, rank_properties

BUDGET_SLABS = [("Below 1 Cr", None, 10_000_000), ("1–2 Cr", 10_000_000, 20_000_000), ("2–3 Cr", 20_000_000, 30_000_000), ("3–4 Cr", 30_000_000, 40_000_000), ("4–5 Cr", 40_000_000, 50_000_000), ("5–6 Cr", 50_000_000, 60_000_000), ("6–7 Cr", 60_000_000, 70_000_000), ("7–8 Cr", 70_000_000, 80_000_000), ("8–9 Cr", 80_000_000, 90_000_000), ("9–10 Cr", 90_000_000, 100_000_000), ("10–12 Cr", 100_000_000, 120_000_000), ("12–15 Cr", 120_000_000, 150_000_000), ("15–20 Cr", 150_000_000, 200_000_000), ("Above 20 Cr", 200_000_000, None)]
BHK_OPTIONS = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "More"]
JODI_OPTIONS = ["1+1", "1+2", "1+3", "1+4", "1+5", "2+1", "2+2", "2+3", "2+4", "2+5", "3+1", "3+2", "3+3", "3+4", "3+5", "4+1", "4+2", "4+3", "4+4", "4+5", "5+1", "5+2", "5+3", "5+4", "5+5"]
CONSTRUCTION_OPTIONS = ["Ready to Move", "Under Construction", "Upcoming", "Sold Out"]
SIDE_OPTIONS = ["East", "West", "Both"]
ALL_CONSTRUCTION_STATUSES = {"ready_to_move", "under_construction", "upcoming", "sold_out"}


def _station_range_filter(filters: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply Mumbai From/To as a strict location constraint."""
    station_from = filters.get("mumbai_station_from")
    station_to = filters.get("mumbai_station_to")
    if not station_from and not station_to:
        return candidates
    corridor = filters.get("mumbai_corridor")
    side = filters.get("mumbai_side", "Both")
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        station = candidate.get("station")
        if not station:
            continue
        if mumbai_station_range_matches(
            property_station=str(station),
            from_station=station_from,
            to_station=station_to,
            side=side,
            property_side=candidate.get("side") or candidate.get("location_side") or "Both",
            corridor=corridor,
        ):
            filtered.append(candidate)
    return filtered


def _location_filter_is_active(filters: dict[str, Any]) -> bool:
    return bool(
        filters.get("preferred_locations") or filters.get("locations") or
        filters.get("locality") or filters.get("pincodes") or
        filters.get("preferred_pincodes") or filters.get("mumbai_station_from") or
        filters.get("mumbai_station_to")
    )


def _strict_preferred_location_filter(filters: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """When the caller enters locations, keep only properties whose structured CRM location contains one of them."""
    requested = filters.get("preferred_locations") or filters.get("locations") or []
    if isinstance(requested, str):
        requested = [requested]
    requested = [str(value).strip().casefold() for value in requested if str(value).strip()]
    if not requested:
        return candidates
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        structured = " ".join(
            str(candidate.get(key) or "")
            for key in ("locality", "location", "sector", "address", "city")
        ).casefold()
        if any(value in structured for value in requested):
            filtered.append(candidate)
    return filtered


def filter_and_rank_properties(filters: dict[str, Any], properties: Iterable[dict[str, Any]]) -> list[MatchCandidate]:
    """Apply hard caller filters, then rank the remaining properties."""
    candidates = list(properties)
    construction = filters.get("construction_statuses") or filters.get("construction_status")
    if construction:
        wanted = {str(v).strip().casefold().replace(" ", "_").replace("-", "_") for v in (construction if isinstance(construction, (list, tuple, set)) else [construction])}
        # All four UI options selected means "Any". In that case there is no
        # construction-status filter at all, including for records with blanks.
        if wanted != ALL_CONSTRUCTION_STATUSES:
            candidates = [
                p for p in candidates
                if str(p.get("construction_status") or "").strip().casefold().replace(" ", "_").replace("-", "_") in wanted
            ]

    if filters.get("city"):
        city = str(filters["city"]).strip().casefold()
        candidates = [p for p in candidates if str(p.get("city") or "").strip().casefold() == city]

    if filters.get("property_type"):
        requested_types = filters["property_type"] if isinstance(filters["property_type"], (list, tuple, set)) else [filters["property_type"]]
        wanted_types = {str(v).strip().casefold() for v in requested_types}
        candidates = [p for p in candidates if str(p.get("property_type") or "").strip().casefold() in wanted_types]

    candidates = _strict_preferred_location_filter(filters, candidates)
    candidates = _station_range_filter(filters, candidates)
    return rank_properties(filters, candidates, minimum_score=0.0)


def group_search_results(results: Iterable[MatchCandidate]) -> dict[str, list[MatchCandidate]]:
    grouped: dict[str, list[MatchCandidate]] = defaultdict(list)
    for result in results:
        grouped[result.location_category].append(result)
    ordered: dict[str, list[MatchCandidate]] = {}
    for category in ("Selected Location", "Other", "All"):
        if category in grouped:
            ordered[category] = grouped[category]
    for category, items in grouped.items():
        if category not in ordered:
            ordered[category] = items
    return ordered


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
