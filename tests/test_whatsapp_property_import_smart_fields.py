from app.services.whatsapp_property_import import parse_property_text


def test_whatsapp_extracts_common_project_contact_and_location_fields():
    parsed = parse_property_text(
        "Project Name: Sethia Pride\n"
        "Developer: Sethia Infrastructure\n"
        "City: Mumbai\n"
        "Locality: Kandivali East\n"
        "Address: Western Express Highway, Kandivali East, Mumbai\n"
        "RERA: P518000046531\n"
        "Contact: +91 9876543210\n"
        "Email: sales@example.com\n"
        "Website: https://example.com\n"
        "Possession: Dec 2028\n"
        "Parking: 1 car\n"
        "Total Units: 240\n"
    )
    assert parsed["project"] == "Sethia Pride"
    assert parsed["developer"] == "Sethia Infrastructure"
    assert parsed["city"] == "Mumbai"
    assert parsed["locality"] == "Kandivali East"
    assert parsed["address"].startswith("Western Express Highway")
    assert parsed["rera"] == "P518000046531"
    assert parsed["contact_phone"] == "+91 9876543210"
    assert parsed["contact_email"] == "sales@example.com"
    assert parsed["website"] == "https://example.com"
    assert parsed["possession_text"] == "Dec 2028"
    assert parsed["parking"] == "1 car"
    assert parsed["total_units"] == "240"


def test_whatsapp_extracts_alternate_configuration_format_without_merging_duplicates():
    parsed = parse_property_text(
        "Sethia Pride Kandivali (E)\n"
        "2 BHK | 850 Sq.ft | ₹2.10 CRORE+\n"
        "2 BHK | 850 Sq.ft | ₹2.10 CRORE+\n"
        "3 BHK: 1200 Sq.ft : ₹3.25 CRORE+\n"
    )
    assert len(parsed["unit_configurations"]) == 2
    assert parsed["unit_configurations"][0]["carpet_area"] == 850
    assert parsed["unit_configurations"][0]["price"] == 21000000.0
    assert parsed["unit_configurations"][1]["carpet_area"] == 1200


def test_map_url_is_kept_separate_from_general_website():
    parsed = parse_property_text(
        "Project: Sethia Pride\n"
        "Map: https://maps.app.goo.gl/abc123\n"
        "Website: https://example.com/project\n"
    )
    assert parsed["map_url"] == "https://maps.app.goo.gl/abc123"
    assert parsed["website"] == "https://example.com/project"
