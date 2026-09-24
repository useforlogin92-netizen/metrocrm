from app.property_master import (
    PropertyUpdateSource,
    normalize_property_payload,
    validate_property_payload,
)


def test_all_four_sources_normalize_to_same_keys():
    raw = {
        "Project Name": "Sample Heights",
        "Property Type": "Residential",
        "BHK": "2 BHK",
        "Carpet Area": "850",
        "Possession Date": "Dec 2027",
        "Full Address": "Andheri East, Mumbai",
        "PIN Code": "400069",
        "BSP": "1.80 Cr",
        "RERA Number": "P51800000000",
    }
    expected = {
        "project_name", "property_type", "configuration", "carpet_area",
        "possession_date", "full_address", "pincode", "bsp",
        "rera_registration_number", "_update_source",
    }
    for source in PropertyUpdateSource:
        normalized = normalize_property_payload(raw, source=source)
        assert set(normalized) == expected
        assert normalized["_update_source"] == source.value


def test_create_validation_requires_only_core_listing_fields():
    payload = normalize_property_payload(
        {
            "Project Name": "Sample Heights",
            "Property Type": "Residential",
            "Configuration": "2 BHK",
            "Possession Date": "Dec 2027",
            "Full Address": "Mumbai",
            "Pincode": "400069",
            "BSP": "1.8 Cr",
        },
        source=PropertyUpdateSource.INDIVIDUAL,
    )
    assert validate_property_payload(payload) == []


def test_invalid_pincode_and_commission_are_rejected():
    payload = normalize_property_payload(
        {
            "Project Name": "Sample",
            "Property Type": "Residential",
            "Configuration": "2 BHK",
            "Possession Date": "2027",
            "Full Address": "Mumbai",
            "Pincode": "4000",
            "BSP": "1 Cr",
            "CP Commission %": "120",
        },
        source="WHATSAPP",
    )
    errors = validate_property_payload(payload)
    assert "Pincode must be a 6-digit Indian PIN" in errors
    assert "CP Commission % must be between 0 and 100" in errors
