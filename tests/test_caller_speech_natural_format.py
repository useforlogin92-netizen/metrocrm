from app.routers.caller_speech import (
    _fallback_script,
    _speech_money,
    _speech_safe_properties,
)


def test_speech_price_uses_natural_lakh_and_crore_words():
    assert _speech_money(9_500_000) == "95 Lakhs"
    assert _speech_money(20_000_000) == "2 Crores"
    assert _speech_money(13_000_000) == "1.3 Crores"


def test_speech_safe_properties_removes_technical_fields_and_normalizes_status():
    safe = _speech_safe_properties([{
        "project": "Green Heights",
        "locality": "Kandivali West",
        "bhk": "2 BHK",
        "carpet_area": 710,
        "price": 9_500_000,
        "rera": "P123456",
        "price_per_sqft": 19000,
        "property_type": "APARTMENT",
        "construction_status": "READY_TO_MOVE",
        "id": 123,
        "score": 99,
    }])
    assert len(safe) == 1
    row = safe[0]
    assert row["price"] == "95 Lakhs"
    assert row["construction_status"] == "ready to move in"
    for key in ("rera", "price_per_sqft", "property_type", "id", "score"):
        assert key not in row


def test_fallback_script_is_conversational_and_omits_technical_data():
    script = _fallback_script([{
        "project": "Green Heights",
        "locality": "Kandivali West",
        "bhk": "2 BHK",
        "carpet_area": 710,
        "price": 9_500_000,
        "rera": "P123456",
        "price_per_sqft": 19000,
        "property_type": "APARTMENT",
        "construction_status": "READY_TO_MOVE",
    }], "hinglish", "full")
    assert "Namaste" in script
    assert "Kandivali West" in script
    assert "95 Lakhs" in script
    assert "site visit" in script.lower()
    for forbidden in ("P123456", "19000", "APARTMENT", "READY_TO_MOVE", "RERA"):
        assert forbidden not in script
