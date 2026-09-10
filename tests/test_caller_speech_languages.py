from types import SimpleNamespace

from app.routers.caller_assistant import _opening_speeches, _property_speeches


def test_opening_speech_has_three_distinct_language_modes():
    user = SimpleNamespace(username="Rahul")
    lead = SimpleNamespace(source="Website", preferred_location="Andheri", bhk="2 BHK")
    customer = SimpleNamespace(name="Amit")
    speeches = _opening_speeches(user, lead, customer, [{"name": "Andheri", "side": "Both", "priority": "Primary"}])

    assert set(speeches) == {"en", "hi", "hinglish"}
    assert speeches["en"] != speeches["hi"]
    assert speeches["en"] != speeches["hinglish"]
    assert "Hello Amit" in speeches["en"]
    assert "नमस्ते Amit" in speeches["hi"]
    assert "Namaste Amit" in speeches["hinglish"]


def test_property_speech_has_three_language_modes_and_keeps_property_data():
    customer = SimpleNamespace(name="Amit")
    property_data = {
        "project": "Green Heights",
        "location": "Andheri West, Mumbai",
        "bhk": "2 BHK",
        "carpet_area": 850.0,
        "price_per_sqft": 20000.0,
        "price": 17000000.0,
        "parking": "1 covered",
        "negotiable": "yes",
        "possession": "Dec 2027",
        "rera": "A12345678",
        "description": "Near metro station",
    }
    speeches = _property_speeches(property_data, customer)

    assert set(speeches) == {"en", "hi", "hinglish"}
    for speech in speeches.values():
        assert "Green Heights" in speech
        assert "Andheri West, Mumbai" in speech
        assert "A12345678" in speech
    assert "suitable option" in speeches["en"]
    assert "उपयुक्त विकल्प" in speeches["hi"]
    assert "suitable option" in speeches["hinglish"]
