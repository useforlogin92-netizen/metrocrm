"""Property catalog field definitions and validation helpers.

The catalog is intentionally metadata-driven so the UI/API can expose a rich
property form without scattering field names across the application.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatalogField:
    key: str
    label: str
    group: str
    field_type: str = "text"
    required: bool = False


PROPERTY_CATALOG_FIELDS: tuple[CatalogField, ...] = (
    CatalogField("property_code", "Property Code", "Basic", required=True),
    CatalogField("title", "Property Title", "Basic", required=True),
    CatalogField("category", "Property Category", "Basic"),
    CatalogField("property_type", "Property Type", "Basic"),
    CatalogField("listing_type", "Buy / Rent", "Basic"),
    CatalogField("listing_status", "Listing Status", "Basic"),
    CatalogField("ownership", "Ownership", "Basic"),
    CatalogField("developer_id", "Developer", "Project"),
    CatalogField("project_id", "Project", "Project"),
    CatalogField("tower_id", "Tower / Wing", "Project"),
    CatalogField("unit_number", "Unit Number", "Unit"),
    CatalogField("state", "State", "Location", required=True),
    CatalogField("district", "District", "Location", required=True),
    CatalogField("city", "City", "Location", required=True),
    CatalogField("locality", "Locality / Area", "Location", required=True),
    CatalogField("sector", "Sector", "Location"),
    CatalogField("pincode", "PIN Code", "Location", required=True),
    CatalogField("address", "Full Address", "Location"),
    CatalogField("landmark", "Landmark", "Location"),
    CatalogField("latitude", "Latitude", "Location", "decimal"),
    CatalogField("longitude", "Longitude", "Location", "decimal"),
    CatalogField("bhk", "BHK / Jodi", "Configuration"),
    CatalogField("bedrooms", "Bedrooms", "Configuration", "integer"),
    CatalogField("bathrooms", "Bathrooms", "Configuration", "integer"),
    CatalogField("balconies", "Balconies", "Configuration", "integer"),
    CatalogField("carpet_area", "Carpet Area", "Area", "decimal"),
    CatalogField("built_up_area", "Built-up Area", "Area", "decimal"),
    CatalogField("super_built_up_area", "Super Built-up Area", "Area", "decimal"),
    CatalogField("plot_area", "Plot Area", "Area", "decimal"),
    CatalogField("terrace_area", "Terrace Area", "Area", "decimal"),
    CatalogField("price", "Price", "Pricing", "decimal"),
    CatalogField("price_per_sqft", "Price / Sq.ft", "Pricing", "decimal"),
    CatalogField("maintenance", "Maintenance", "Pricing", "decimal"),
    CatalogField("other_charges", "Other Charges", "Pricing", "decimal"),
    CatalogField("negotiable", "Negotiable", "Pricing", "boolean"),
    CatalogField("parking", "Parking", "Parking"),
    CatalogField("parking_count", "Parking Count", "Parking", "integer"),
    CatalogField("facing", "Facing", "Features"),
    CatalogField("view", "View", "Features"),
    CatalogField("furnishing", "Furnishing", "Features"),
    CatalogField("amenities", "Amenities", "Features", "multi"),
    CatalogField("construction_status", "Construction Status", "Construction"),
    CatalogField("possession_date", "Expected Possession", "Construction", "date"),
    CatalogField("rera_number", "RERA Number", "Legal"),
    CatalogField("rera_possession_date", "RERA Possession Date", "Legal", "date"),
    CatalogField("builder_commitment_date", "Builder Commitment Date", "Legal", "date"),
    CatalogField("oc_status", "OC Status", "Legal"),
    CatalogField("cc_status", "CC Status", "Legal"),
    CatalogField("loan_available", "Loan Available", "Legal", "boolean"),
    CatalogField("description", "Property Description", "Marketing", "textarea"),
    CatalogField("highlights", "Property Highlights", "Marketing", "textarea"),
    CatalogField("internal_notes", "Internal Notes", "Internal", "textarea"),
)

MEDIA_TYPES = ("IMAGE", "VIDEO", "BROCHURE", "FLOOR_PLAN", "PRICE_SHEET", "DOCUMENT", "OTHER")


def catalog_groups() -> dict[str, tuple[CatalogField, ...]]:
    groups: dict[str, list[CatalogField]] = {}
    for field in PROPERTY_CATALOG_FIELDS:
        groups.setdefault(field.group, []).append(field)
    return {name: tuple(fields) for name, fields in groups.items()}


def validate_pincode(pincode: str | None) -> bool:
    """Validate an Indian six-digit PIN code when supplied."""
    return pincode is None or (len(pincode) == 6 and pincode.isdigit())
