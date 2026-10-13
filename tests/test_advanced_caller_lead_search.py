from pathlib import Path

from app.routers.caller_search import _LEAD_STATUS_GROUPS, _ALLOWED_DISPOSITION_STATUSES


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
