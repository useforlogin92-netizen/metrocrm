from app.property_catalog import MEDIA_TYPES, catalog_groups, validate_pincode


def test_catalog_contains_location_and_rich_detail_groups():
    groups = catalog_groups()
    assert {"Basic", "Location", "Configuration", "Area", "Pricing", "Parking", "Features", "Construction", "Legal", "Marketing", "Internal"}.issubset(groups)
    keys = {field.key for field in groups["Location"]}
    assert {"state", "district", "city", "locality", "pincode", "address"}.issubset(keys)
    assert {"rera_number", "rera_possession_date", "builder_commitment_date"}.issubset(
        {field.key for field in groups["Legal"]}
    )


def test_media_types_support_catalog_assets():
    assert {"IMAGE", "VIDEO", "BROCHURE", "FLOOR_PLAN", "PRICE_SHEET", "DOCUMENT", "OTHER"}.issubset(MEDIA_TYPES)


def test_indian_pincode_validation():
    assert validate_pincode("400001")
    assert not validate_pincode("40001")
    assert not validate_pincode("40000A")
