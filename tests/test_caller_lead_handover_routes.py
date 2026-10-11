from app.main import app


def test_caller_report_and_transfer_routes_are_registered():
    routes = [
        route for route in app.routes
        if getattr(route, "path", None) in {
            "/admin/lead-monitoring/report/{lead_id}",
            "/admin/lead-monitoring/transfer-lead",
        }
    ]
    route_methods = {(route.path, method) for route in routes for method in (getattr(route, "methods", None) or set())}
    assert ("/admin/lead-monitoring/report/{lead_id}", "GET") in route_methods
    assert ("/admin/lead-monitoring/transfer-lead", "POST") in route_methods

from datetime import datetime, timedelta

from app.models import FollowUp, Lead
from app.routers.lead_visit_monitoring import _lead_health_score


def _lead(*, assigned_user_id=7, status="CONTACTED", age_days=0):
    return Lead(
        id=123,
        source="Test",
        status=status,
        assigned_user_id=assigned_user_id,
        created_at=datetime.now() - timedelta(days=age_days),
    )


def test_healthy_lead_has_full_score_when_followup_is_not_overdue():
    now = datetime.now()
    lead = _lead()
    followup = FollowUp(
        id=1, lead_id=lead.id, assigned_user_id=lead.assigned_user_id,
        due_at=now + timedelta(hours=2), completed=False,
    )
    score, reasons = _lead_health_score(lead, [followup], now)
    assert score == 100
    assert reasons == ["No rule-based risk flags"]


def test_unassigned_overdue_lead_is_flagged_for_manager_review():
    now = datetime.now()
    lead = _lead(assigned_user_id=None, status="NEW", age_days=4)
    followup = FollowUp(
        id=2, lead_id=lead.id, assigned_user_id=7,
        due_at=now - timedelta(hours=1), completed=False,
    )
    score, reasons = _lead_health_score(lead, [followup], now)
    assert score < 60
    assert "Unassigned" in reasons
    assert "1 overdue follow-up(s)" in reasons
    assert "Lead status has not progressed" in reasons


def test_completed_followup_does_not_count_as_overdue():
    now = datetime.now()
    lead = _lead()
    followup = FollowUp(
        id=3, lead_id=lead.id, assigned_user_id=lead.assigned_user_id,
        due_at=now - timedelta(hours=1), completed=True,
    )
    score, reasons = _lead_health_score(lead, [followup], now)
    assert score == 100
    assert "1 overdue follow-up(s)" not in reasons
