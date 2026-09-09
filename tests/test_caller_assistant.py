from types import SimpleNamespace

from app.routers.caller_assistant import _lead_locations, _opening_speech, _property_speech


def test_multiple_locations_preserve_side_and_priority():
    lead = SimpleNamespace(preferred_location="Borivali, Andheri")
    requirement = SimpleNamespace(locations_json='[{"name":"Borivali","side":"Both","priority":"Primary"},{"name":"Andheri","side":"West","priority":"Secondary"}]')
    assert _lead_locations(lead, requirement) == [
        {"name":"Borivali","side":"Both","priority":"Primary"},
        {"name":"Andheri","side":"West","priority":"Secondary"},
    ]


def test_opening_speech_uses_source_and_caller_name():
    user = SimpleNamespace(username="Suresh")
    lead = SimpleNamespace(source="MagicBricks", preferred_location="Borivali, Andheri", bhk="2 BHK")
    customer = SimpleNamespace(name="Rahul")
    text = _opening_speech(user, lead, customer, [{"name":"Borivali","side":"Both","priority":"Primary"},{"name":"Andheri","side":"Both","priority":"Primary"}])
    assert "Suresh" in text
    assert "MagicBricks" in text
    assert "Rahul" in text
    assert "Borivali, Andheri" in text
    assert "2 BHK" in text


def test_property_speech_contains_sales_details():
    customer = SimpleNamespace(name="Rahul")
    property_data = {
        "project":"ABC Residency", "location":"Borivali West", "bhk":"2 BHK",
        "carpet_area":650.0, "price_per_sqft":12000.0, "price":7800000.0,
        "parking":"2", "negotiable":"Yes", "possession":"Dec 2027", "rera":"P123",
        "description":"Near station",
    }
    text = _property_speech(property_data, customer)
    for expected in ("ABC Residency","Borivali West","2 BHK","650","12,000","7,800,000","2","negotiable","Dec 2027","P123"):
        assert expected in text

# CI trigger after the call-assistant integration.
