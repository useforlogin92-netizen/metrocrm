"""Canonical Property Master schema and normalization pipeline.

All property intake/update channels must normalize into this contract before
persistence: individual edit, bulk import, WhatsApp intake, and SM secure-link.
The schema deliberately keeps optional marketing/media fields optional.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import re
from typing import Any, Mapping


class PropertyUpdateSource(StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    BULK = "BULK"
    WHATSAPP = "WHATSAPP"
    SM_LINK = "SM_LINK"


@dataclass(frozen=True, slots=True)
class PropertyField:
    key: str
    label: str
    group: str
    required_on_create: bool = False
    field_type: str = "text"


PROPERTY_MASTER_FIELDS: tuple[PropertyField, ...] = (
    PropertyField("project_name", "Project Name", "Basic", True),
    PropertyField("property_type", "Property Type", "Basic", True),
    PropertyField("configuration", "Configuration", "Basic", True),
    PropertyField("carpet_area", "Carpet Area", "Basic"),
    PropertyField("possession_date", "Possession Date", "Basic", True, "date"),
    PropertyField("full_address", "Full Address", "Location", True),
    PropertyField("pincode", "Pincode", "Location", True),
    PropertyField("google_maps_link", "Google Maps Link", "Location"),
    PropertyField("nearby_connectivity", "Nearby Connectivity / Landmarks", "Location"),
    PropertyField("bsp", "Base Selling Price (BSP)", "Financial", True),
    PropertyField("configurations", "Configuration Details", "Financial", field_type="repeater"),
    PropertyField("negotiation", "Negotiation", "Financial"),
    PropertyField("additional_government_charges", "Additional / Government Charges", "Financial"),
    PropertyField("payment_plan", "Payment Plan", "Financial"),
    PropertyField("cp_commission_percent", "CP Commission %", "Financial"),
    PropertyField("rera_registration_number", "RERA Registration Number", "Legal"),
    PropertyField("approved_banks", "Approved Banks List", "Legal"),
    PropertyField("title_deed_type", "Title Deed Type", "Legal"),
    PropertyField("site_flat_photos", "High-Res Site / Flat Photos", "Media", field_type="media"),
    PropertyField("floor_plan", "Floor Plan", "Media", field_type="media"),
    PropertyField("master_layout", "Master Layout", "Media", field_type="media"),
    PropertyField("project_pdf_brochure", "Project PDF Brochure", "Media", field_type="media"),
    PropertyField("walkthrough_video_link", "Walkthrough Video Link", "Media"),
    PropertyField("rm_name", "Relationship Manager (RM)", "CP / Sales"),
    PropertyField("rm_contact", "RM Contact Info", "CP / Sales"),
    PropertyField("site_visit_timings", "Site Visit Timings", "CP / Sales"),
    PropertyField("booking_process", "Booking Process", "CP / Sales"),
)


ALIASES: dict[str, str] = {
    "project": "project_name",
    "project name": "project_name",
    "project_name": "project_name",
    "type": "property_type",
    "property type": "property_type",
    "property_type": "property_type",
    "bhk": "configuration",
    "configuration": "configuration",
    "carpet": "carpet_area",
    "carpet area": "carpet_area",
    "carpet_area": "carpet_area",
    "possession": "possession_date",
    "possession date": "possession_date",
    "possession_date": "possession_date",
    "address": "full_address",
    "full address": "full_address",
    "full_address": "full_address",
    "pin": "pincode",
    "pin code": "pincode",
    "pincode": "pincode",
    "google maps": "google_maps_link",
    "google maps link": "google_maps_link",
    "maps link": "google_maps_link",
    "bsp": "bsp",
    "configuration details": "configurations",
    "configurations": "configurations",
    "configuration details json": "configurations",
    "negotiation": "negotiation",
    "base selling price": "bsp",
    "base selling price (bsp)": "bsp",
    "charges": "additional_government_charges",
    "additional charges": "additional_government_charges",
    "government charges": "additional_government_charges",
    "payment plan": "payment_plan",
    "cp commission": "cp_commission_percent",
    "cp commission %": "cp_commission_percent",
    "rera": "rera_registration_number",
    "rera number": "rera_registration_number",
    "rera registration number": "rera_registration_number",
    "approved banks": "approved_banks",
    "approved banks list": "approved_banks",
    "title deed": "title_deed_type",
    "title deed type": "title_deed_type",
    "rm": "rm_name",
    "rm name": "rm_name",
    "rm contact": "rm_contact",
    "site visit timings": "site_visit_timings",
    "booking process": "booking_process",
}


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " "))


def canonicalize_key(value: Any) -> str | None:
    normalized = _key(value)
    if normalized in ALIASES:
        return ALIASES[normalized]
    valid = {field.key for field in PROPERTY_MASTER_FIELDS}
    return normalized.replace(" ", "_") if normalized.replace(" ", "_") in valid else None


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize_property_payload(
    payload: Mapping[str, Any],
    *,
    source: PropertyUpdateSource | str,
) -> dict[str, Any]:
    """Map any supported intake payload into the canonical Property Master keys."""
    source_value = PropertyUpdateSource(str(source).upper()).value
    result: dict[str, Any] = {}
    for raw_key, raw_value in payload.items():
        key = canonicalize_key(raw_key)
        if key is None:
            continue
        value = _clean(raw_value)
        if value is not None:
            result[key] = value

    if "configurations" in result and isinstance(result["configurations"], list):
        normalized_rows = []
        for row in result["configurations"]:
            if not isinstance(row, Mapping):
                continue
            item = {str(k): v for k, v in row.items() if v not in (None, "")}
            area = item.get("carpet_area")
            total = item.get("price_including_all")
            rate = item.get("rate_per_sqft")
            try:
                area_n = float(area) if area is not None else None
                total_n = float(total) if total is not None else None
                rate_n = float(rate) if rate is not None else None
                if total_n is None and rate_n is not None and area_n:
                    total_n = round(area_n * rate_n, 2)
                elif rate_n is None and total_n is not None and area_n:
                    rate_n = round(total_n / area_n, 2)
                if area_n is not None:
                    item["carpet_area"] = area_n
                if total_n is not None:
                    item["price_including_all"] = total_n
                if rate_n is not None:
                    item["rate_per_sqft"] = rate_n
            except (TypeError, ValueError, ZeroDivisionError):
                pass
            if "negotiation" in item:
                item["negotiation"] = str(item["negotiation"]).strip().upper()
            normalized_rows.append(item)
        result["configurations"] = normalized_rows

    # Keep source as system metadata, not user-editable property content.
    result["_update_source"] = source_value
    return result


def validate_property_payload(
    payload: Mapping[str, Any],
    *,
    is_create: bool = True,
) -> list[str]:
    """Return validation errors without rejecting optional/unknown source data."""
    errors: list[str] = []
    if is_create:
        for field in PROPERTY_MASTER_FIELDS:
            if field.required_on_create and not _clean(payload.get(field.key)):
                errors.append(f"{field.label} is required")

    pincode = _clean(payload.get("pincode"))
    if pincode is not None and (not str(pincode).isdigit() or len(str(pincode)) != 6):
        errors.append("Pincode must be a 6-digit Indian PIN")

    commission = _clean(payload.get("cp_commission_percent"))
    if commission is not None:
        try:
            number = float(str(commission).replace("%", "").strip())
            if number < 0 or number > 100:
                errors.append("CP Commission % must be between 0 and 100")
        except ValueError:
            errors.append("CP Commission % must be numeric")

    configurations = payload.get("configurations")
    if configurations is not None:
        if not isinstance(configurations, list):
            errors.append("Configuration Details must be a list")
        else:
            for index, row in enumerate(configurations, start=1):
                if not isinstance(row, Mapping):
                    errors.append(f"Configuration row {index} is invalid")
                    continue
                config = _clean(row.get("configuration"))
                area = _clean(row.get("carpet_area"))
                total = _clean(row.get("price_including_all"))
                rate = _clean(row.get("rate_per_sqft"))
                if not config:
                    errors.append(f"Configuration row {index}: Configuration is required")
                if area is None:
                    errors.append(f"Configuration row {index}: Carpet Area is required")
                if total is None and rate is None:
                    errors.append(f"Configuration row {index}: enter Total Price (Including All) or Rate / Sq Ft")
                negotiation = row.get("negotiation")
                if negotiation is not None and str(negotiation).upper() not in {"YES", "NO"}:
                    errors.append(f"Configuration row {index}: Negotiation must be Yes or No")

    maps_link = _clean(payload.get("google_maps_link"))
    if maps_link is not None and not str(maps_link).lower().startswith(("http://", "https://")):
        errors.append("Google Maps Link must be a valid HTTP/HTTPS URL")

    return errors


def property_field_groups() -> dict[str, tuple[PropertyField, ...]]:
    groups: dict[str, list[PropertyField]] = {}
    for field in PROPERTY_MASTER_FIELDS:
        groups.setdefault(field.group, []).append(field)
    return {group: tuple(fields) for group, fields in groups.items()}


CONFIGURATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("configuration", "Configuration (e.g. 1 BHK)"),
    ("carpet_area", "Carpet Area (Sq Ft)"),
    ("price_including_all", "Total Price (Including All)"),
    ("rate_per_sqft", "Rate / Sq Ft"),
    ("negotiation", "Negotiation (Yes/No)"),
)
