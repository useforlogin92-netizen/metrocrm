from app.routers.caller_speech import _fallback_script, _group_properties


def _property(name, location, bhk="2 BHK", price=15000000):
    return {
        "project": name,
        "locality": location,
        "bhk": bhk,
        "property_type": "Apartment",
        "price": price,
        "carpet_area": 900,
        "construction_status": "Under Construction",
        "possession": "Dec 2027",
    }


def test_group_properties_by_location():
    grouped = _group_properties([
        _property("A", "Kandivali"),
        _property("B", "Malad"),
        _property("C", "Kandivali"),
        _property("D", "Jogeshwari"),
    ])
    assert list(grouped) == ["Kandivali", "Malad", "Jogeshwari"]
    assert len(grouped["Kandivali"]) == 2
    assert len(grouped["Malad"]) == 1


def test_fallback_script_contains_all_locations_and_properties():
    properties = [
        _property("Kandivali One", "Kandivali"),
        _property("Kandivali Two", "Kandivali", "3 BHK"),
        _property("Malad One", "Malad"),
        _property("Jogeshwari One", "Jogeshwari"),
        _property("Andheri One", "Andheri"),
        _property("Andheri Two", "Andheri", "3 BHK"),
    ]
    text = _fallback_script(properties, "hinglish", "full")
    for name in ["Kandivali One", "Kandivali Two", "Malad One", "Jogeshwari One", "Andheri One", "Andheri Two"]:
        assert name in text
    for location in ["Kandivali", "Malad", "Jogeshwari", "Andheri"]:
        assert location in text


def test_summary_script_omits_optional_full_details():
    text = _fallback_script([_property("Summary Home", "Malad")], "en", "summary")
    assert "Summary Home" in text
    assert "900 sq.ft. carpet area" not in text
