from app.property_master import (
    PropertyUpdateSource,
    normalize_property_payload,
    validate_property_payload,
)


def _canonical_payload():
    return {
        "Property Ref": "P-001",
        "Developer / Builder": "Example Developer",
        "Project Name": "Sample Heights",
        "Property Type": "Residential",
        "Listing Status": "Active",
        "Availability Status": "Available",
        "Full Address": "Andheri East, Mumbai",
        "City": "Mumbai",
        "Locality / Area": "Andheri East",
        "Pincode": "400069",
        "Google Maps Link": "https://maps.google.com/?q=Andheri+East",
        "Nearby Connectivity / Landmarks": "Metro, station, school",
        "Project Status": "Under Construction",
        "Possession Date": "Dec 2027",
        "Total Towers": 2,
        "RERA Registration Number": "P51800000000",
        "Approved Banks List": "HDFC, ICICI",
        "Title Deed Type": "Freehold",
        "Configuration Details": [
            {
                "configuration": "2 BHK",
                "carpet_area": 850,
                "price_including_all": 18000000,
                "negotiation": "Yes",
                "availability": "Available",
            }
        ],
        "Additional / Government Charges": "As applicable",
        "Payment Plan": "20:80",
        "CP Commission %": 2,
        "Amenities & Facilities": "Car Parking, Gym, Lift, CCTV",
        "Other Facility": "Sample facility",
        "Walkthrough Video Link": "https://example.com/video",
        "Relationship Manager (RM)": "RM Name",
        "RM Contact Info": "9999999999",
        "Site Visit Timings": "10 AM - 6 PM",
        "Booking Process": "Token + KYC",
    }


def test_all_four_sources_normalize_to_same_canonical_keys():
    raw = _canonical_payload()
    expected = set(normalize_property_payload(raw, source=PropertyUpdateSource.INDIVIDUAL))
    for source in PropertyUpdateSource:
        normalized = normalize_property_payload(raw, source=source)
        assert set(normalized) == expected
        assert normalized["_update_source"] == source.value
    assert "configurations" in expected
    assert "configuration" not in expected
    assert "bsp" not in expected


def test_create_validation_accepts_complete_v3_property_master():
    payload = normalize_property_payload(_canonical_payload(), source=PropertyUpdateSource.INDIVIDUAL)
    assert validate_property_payload(payload) == []


def test_invalid_pincode_and_commission_are_rejected():
    raw = _canonical_payload()
    raw["Pincode"] = "4000"
    raw["CP Commission %"] = "120"
    payload = normalize_property_payload(raw, source="WHATSAPP")
    errors = validate_property_payload(payload)
    assert "Pincode must be a 6-digit Indian PIN" in errors
    assert "CP Commission % must be between 0 and 100" in errors


def test_configuration_pricing_auto_calculates_missing_side():
    payload = normalize_property_payload(
        {
            "Project Name": "Sample",
            "Property Type": "Residential",
            "Configuration Details": [
                {"configuration": "1 BHK", "carpet_area": 650, "price_including_all": 8450000, "negotiation": "Yes"},
                {"configuration": "1 BHK", "carpet_area": 700, "rate_per_sqft": 14000, "negotiation": "No"},
            ],
        },
        source="BULK",
    )
    rows = payload["configurations"]
    assert rows[0]["rate_per_sqft"] == round(8450000 / 650, 2)
    assert rows[1]["price_including_all"] == 9800000.0
