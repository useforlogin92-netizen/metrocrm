from app.routers.caller_search import CALLER_ROLES, _LEAD_STATUS_GROUPS, _ALLOWED_DISPOSITION_STATUSES
from app.routers.caller_speech import _fallback_script, _speech_money, _speech_safe_properties
from pathlib import Path


def test_quick_lead_status_filters_map_to_supported_crm_statuses():
    assert _LEAD_STATUS_GROUPS["HOT"] == {"QUALIFIED", "SITE_VISIT_SCHEDULED", "NEGOTIATION", "BOOKED"}
    assert _LEAD_STATUS_GROUPS["WARM"] == {"CONTACTED", "FOLLOW_UP_REQUIRED"}
    assert _LEAD_STATUS_GROUPS["COLD"] == {"LOST", "NOT_INTERESTED"}
    assert _LEAD_STATUS_GROUPS["SITE_VISIT_BOOKED"] == {"SITE_VISIT_SCHEDULED"}


def test_disposition_statuses_are_restricted_to_supported_values():
    assert "SITE_VISIT_SCHEDULED" in _ALLOWED_DISPOSITION_STATUSES
    assert "BOOKED" in _ALLOWED_DISPOSITION_STATUSES
    assert "UNAUTHORIZED_STATUS" not in _ALLOWED_DISPOSITION_STATUSES


def test_caller_search_template_has_advanced_lead_actions_and_property_matching():
    template = Path("app/templates/caller_search.html").read_text(encoding="utf-8")
    for expected in (
        "Lead Search & Quick Actions",
        "leadBudget",
        "leadBhk",
        "leadLocation",
        "leadStatus",
        "/caller/search/leads",
        "/disposition",
        "tel:",
        "wa.me/",
        "matchLeadToProperties",
        "Update Lead Disposition",
        "X-CSRF-Token",
        "function humanStatus",
    ):
        assert expected in template


def test_speech_prices_are_natural_and_trim_trailing_zeros():
    assert _speech_money(9_500_000) == "95 Lakhs"
    assert _speech_money(20_000_000) == "2 Crores"
    assert _speech_money(13_000_000) == "1.3 Crores"


def test_speech_input_excludes_technical_property_fields():
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
    assert safe[0]["price"] == "95 Lakhs"
    assert safe[0]["construction_status"] == "ready to move in"
    for key in ("rera", "price_per_sqft", "property_type", "id", "score"):
        assert key not in safe[0]


def test_fallback_speech_is_natural_and_omits_technical_values():
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


def test_search_workspace_is_available_to_every_defined_user_category():
    assert CALLER_ROLES == {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER", "ACCOUNTANT", "HR"}
