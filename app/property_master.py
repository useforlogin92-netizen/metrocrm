"""Fresh canonical Metro Property Master contract.

One canonical structure for Individual, Bulk, WhatsApp and SM secure-link intake.
The UI deliberately excludes unit/floor/facing/furnishing/parking-at-unit fields.
Parking is a project-level amenity.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    PropertyField("property_ref", "Property Ref", "Identification"),
    PropertyField("developer", "Developer / Builder", "Identification"),
    PropertyField("project_name", "Project Name", "Identification", True),
    PropertyField("property_type", "Property Type", "Identification", True),
    PropertyField("listing_status", "Listing Status", "Identification"),
    PropertyField("availability_status", "Availability Status", "Identification"),
    PropertyField("full_address", "Full Address", "Location", True),
    PropertyField("city", "City", "Location", True),
    PropertyField("locality", "Locality / Area", "Location", True),
    PropertyField("pincode", "Pincode", "Location", True),
    PropertyField("google_maps_link", "Google Maps Link", "Location"),
    PropertyField("nearby_connectivity", "Nearby Connectivity / Landmarks", "Location"),
    PropertyField("project_status", "Project Status", "Project Details"),
    PropertyField("possession_date", "Possession Date", "Project Details", field_type="date"),
    PropertyField("total_towers", "Total Towers", "Project Details", field_type="number"),
    PropertyField("tower_details", "Tower Details", "Project Details", field_type="repeater"),
    PropertyField("rera_registration_number", "RERA Registration Number", "Legal"),
    PropertyField("approved_banks", "Approved Banks List", "Legal"),
    PropertyField("title_deed_type", "Title Deed Type", "Legal"),
    PropertyField("configurations", "Configuration Details", "Configuration", True, "repeater"),
    PropertyField("additional_government_charges", "Additional / Government Charges", "Financial"),
    PropertyField("payment_plan", "Payment Plan", "Financial"),
    PropertyField("cp_commission_percent", "CP Commission %", "Financial"),
    PropertyField("facilities", "Amenities & Facilities", "Amenities", field_type="checkboxes"),
    PropertyField("other_facility", "Other Facility", "Amenities"),
    PropertyField("site_flat_photos", "High-Res Site / Flat Photos", "Media", field_type="media"),
    PropertyField("floor_plan", "Floor Plan", "Media", field_type="media"),
    PropertyField("master_layout", "Master Layout", "Media", field_type="media"),
    PropertyField("project_pdf_brochure", "Project PDF Brochure", "Media", field_type="media"),
    PropertyField("walkthrough_video_link", "Walkthrough Video Link", "Media"),
    PropertyField("rm_name", "Relationship Manager (RM)", "CP / Sales"),
    PropertyField("rm_contact", "RM Contact Info", "CP / Sales"),
    PropertyField("site_visit_timings", "Site Visit Timings", "CP / Sales"),
    PropertyField("booking_process", "Booking Process", "CP / Sales"),
    PropertyField("last_updated_date", "Last Updated Date", "Source Tracking", field_type="date"),
    PropertyField("data_source", "Data Source", "Source Tracking"),
)


FACILITY_GROUPS: dict[str, tuple[str, ...]] = {
    "Parking": (
        "Car Parking", "Covered Car Parking", "Open Car Parking",
        "Visitor Parking", "Two-Wheeler Parking", "EV Charging",
    ),
    "Security & Safety": (
        "24x7 Security", "CCTV", "Gated Community", "Security Intercom",
        "Video Door Phone", "Visitor Management", "Fire Safety System", "Access Control",
    ),
    "Fitness & Wellness": (
        "Gym", "Swimming Pool", "Jogging Track", "Walking Track",
        "Yoga / Meditation Area", "Sports Room", "Indoor Games",
    ),
    "Kids & Family": (
        "Children's Play Area", "Creche / Day Care", "Senior Citizen Area", "Kids Pool",
    ),
    "Sports": (
        "Badminton Court", "Basketball Court", "Tennis Court",
        "Cricket Practice Area", "Football Area", "Table Tennis", "Outdoor Games",
    ),
    "Club & Social": (
        "Club House", "Multipurpose Hall", "Party Hall", "Community Hall",
        "Library", "Lounge", "Cafeteria",
    ),
    "Green & Outdoor": (
        "Garden", "Landscaped Garden", "Rooftop Garden", "Terrace", "Pet Area",
    ),
    "Building & Utilities": (
        "Lift", "Power Backup", "Water Supply", "Rainwater Harvesting",
        "Solar Power", "Sewage Treatment Plant", "Waste Management",
    ),
    "Convenience": (
        "Convenience Store", "ATM", "Pharmacy", "Laundry", "Car Wash",
        "Parcel / Delivery Room", "Guest Rooms",
    ),
}


ALIASES: dict[str, str] = {
    "property ref": "property_ref", "property_ref": "property_ref",
    "developer": "developer", "builder": "developer", "developer / builder": "developer",
    "project": "project_name", "project name": "project_name", "project_name": "project_name",
    "type": "property_type", "property type": "property_type", "property_type": "property_type",
    "listing status": "listing_status", "availability status": "availability_status",
    "address": "full_address", "full address": "full_address", "full_address": "full_address",
    "city": "city", "locality": "locality", "locality / area": "locality",
    "pin": "pincode", "pin code": "pincode", "pincode": "pincode",
    "google maps": "google_maps_link", "google maps link": "google_maps_link", "maps link": "google_maps_link",
    "nearby": "nearby_connectivity", "nearby connectivity": "nearby_connectivity",
    "project status": "project_status", "possession": "possession_date", "possession date": "possession_date",
    "possession_date": "possession_date", "total towers": "total_towers", "tower details": "tower_details",
    "towers": "tower_details",
    "rera": "rera_registration_number", "rera number": "rera_registration_number",
    "rera registration number": "rera_registration_number",
    "approved banks": "approved_banks", "approved banks list": "approved_banks",
    "title deed": "title_deed_type", "title deed type": "title_deed_type",
    "configuration": "configurations", "configurations": "configurations",
    "configuration details": "configurations", "configuration details json": "configurations",
    "charges": "additional_government_charges", "additional charges": "additional_government_charges",
    "government charges": "additional_government_charges",
    "payment plan": "payment_plan", "cp commission": "cp_commission_percent",
    "cp commission %": "cp_commission_percent",
    "amenities": "facilities", "amenities & facilities": "facilities", "facilities": "facilities",
    "other facility": "other_facility",
    "rm": "rm_name", "rm name": "rm_name", "rm contact": "rm_contact",
    "site visit timings": "site_visit_timings", "booking process": "booking_process",
}


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " "))


def canonicalize_key(value: Any) -> str | None:
    normalized = _key(value)
    if normalized in ALIASES:
        return ALIASES[normalized]
    key = normalized.replace(" ", "_")
    return key if key in {f.key for f in PROPERTY_MASTER_FIELDS} else None


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = re.split(r"[,;|\n]+", str(value))
    return [str(v).strip() for v in raw if str(v).strip()]


def normalize_property_payload(payload: Mapping[str, Any], *, source: PropertyUpdateSource | str) -> dict[str, Any]:
    source_value = PropertyUpdateSource(str(source).upper()).value
    result: dict[str, Any] = {}
    for raw_key, raw_value in payload.items():
        key = canonicalize_key(raw_key)
        if key is None:
            continue
        value = _clean(raw_value)
        if value is not None:
            result[key] = value

    rows = result.get("configurations")
    if isinstance(rows, list):
        normalized_rows = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            item = {str(k): v for k, v in row.items() if v not in (None, "")}
            for number_key in ("carpet_area", "price_including_all", "rate_per_sqft", "bundle_rate"):
                try:
                    if item.get(number_key) not in (None, ""):
                        item[number_key] = float(item[number_key])
                except (TypeError, ValueError):
                    pass
            area = item.get("carpet_area")
            total = item.get("price_including_all")
            rate = item.get("rate_per_sqft")
            bundle = item.get("bundle_rate")
            if total is None and bundle is not None:
                item["price_including_all"] = bundle
                total = bundle
            if total is None and rate is not None and area:
                item["price_including_all"] = round(float(area) * float(rate), 2)
            elif rate is None and total is not None and area:
                item["rate_per_sqft"] = round(float(total) / float(area), 2)
            if "negotiation" in item:
                item["negotiation"] = str(item["negotiation"]).strip().upper()
            if "availability" in item:
                item["availability"] = str(item["availability"]).strip()
            normalized_rows.append(item)
        result["configurations"] = normalized_rows

    towers = result.get("tower_details")
    if isinstance(towers, list):
        clean_towers = []
        for row in towers:
            if not isinstance(row, Mapping):
                continue
            item = {str(k): v for k, v in row.items() if v not in (None, "")}
            if item.get("total_floors") not in (None, ""):
                try:
                    item["total_floors"] = int(item["total_floors"])
                except (TypeError, ValueError):
                    pass
            clean_towers.append(item)
        result["tower_details"] = clean_towers

    if "facilities" in result:
        result["facilities"] = _listify(result["facilities"])

    result["_update_source"] = source_value
    return result


def validate_property_payload(payload: Mapping[str, Any], *, is_create: bool = True, allow_incomplete_configurations: bool = False) -> list[str]:
    errors: list[str] = []
    if is_create:
        allow_incomplete_master = bool(payload.get("_allow_incomplete_master"))
        for field in PROPERTY_MASTER_FIELDS:
            if field.required_on_create and not _clean(payload.get(field.key)) and not allow_incomplete_master:
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

    for i, row in enumerate(payload.get("configurations") or [], 1):
        if not isinstance(row, Mapping):
            errors.append(f"Configuration row {i} is invalid")
            continue
        if not _clean(row.get("configuration")):
            errors.append(f"Configuration row {i}: Configuration is required")
        if not allow_incomplete_configurations:
            if _clean(row.get("carpet_area")) is None:
                errors.append(f"Configuration row {i}: Carpet Area is required")
            if (_clean(row.get("price_including_all")) is None and
                    _clean(row.get("rate_per_sqft")) is None and
                    _clean(row.get("bundle_rate")) is None):
                errors.append(f"Configuration row {i}: enter Total Price, Per Square Rate or Bundle Rate")
        if str(row.get("negotiation", "")).upper() not in {"", "YES", "NO"}:
            errors.append(f"Configuration row {i}: Negotiation must be Yes or No")

    for i, row in enumerate(payload.get("tower_details") or [], 1):
        if not _clean(row.get("tower_name")):
            errors.append(f"Tower row {i}: Tower Name is required")
        floors = row.get("total_floors")
        if floors not in (None, ""):
            try:
                if int(floors) < 1:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"Tower row {i}: Total Floors must be a positive number")

    maps = _clean(payload.get("google_maps_link"))
    if maps and not str(maps).lower().startswith(("http://", "https://")):
        errors.append("Google Maps Link must be a valid HTTP/HTTPS URL")
    return errors


def property_field_groups() -> dict[str, tuple[PropertyField, ...]]:
    groups: dict[str, list[PropertyField]] = {}
    for field in PROPERTY_MASTER_FIELDS:
        groups.setdefault(field.group, []).append(field)
    return {k: tuple(v) for k, v in groups.items()}


CONFIGURATION_COLUMNS = (
    ("configuration", "Configuration"),
    ("carpet_area", "Carpet Area (Sq Ft)"),
    ("price_including_all", "Total Price (Including All)"),
    ("rate_per_sqft", "Per Square Rate"),
    ("bundle_rate", "Bundle Rate"),
    ("negotiation", "Negotiation (Yes/No)"),
    ("availability", "Availability"),
)

TOWER_COLUMNS = (
    ("tower_name", "Tower Name"),
    ("total_floors", "Total Floors"),
    ("possession_date", "Possession Date"),
)
