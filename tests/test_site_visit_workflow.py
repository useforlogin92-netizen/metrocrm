from types import SimpleNamespace

from app.routers.site_visit_workflow import _visible_lead
from app.site_visit_workflow_models import SiteVisitReview


def test_admin_and_super_admin_can_manage_any_lead_visit():
    lead = SimpleNamespace(assigned_user_id=900)
    assert _visible_lead(SimpleNamespace(role="SUPER_ADMIN", id=1), lead)
    assert _visible_lead(SimpleNamespace(role="ADMIN", id=2), lead)


def test_non_admin_can_only_manage_visits_for_assigned_lead():
    actor = SimpleNamespace(role="SALES_EXECUTIVE", id=10)
    assert _visible_lead(actor, SimpleNamespace(assigned_user_id=10))
    assert not _visible_lead(actor, SimpleNamespace(assigned_user_id=11))
    assert not _visible_lead(actor, SimpleNamespace(assigned_user_id=None))


def test_visit_review_is_separate_from_existing_site_visit_schema():
    # Keep live SiteVisit schema untouched; detailed post-visit data lives in its own table.
    assert SiteVisitReview.__tablename__ == "site_visit_reviews"
    assert "called_by_id" in SiteVisitReview.__table__.columns
    assert "sm_id" in SiteVisitReview.__table__.columns
    assert "customer_feedback" in SiteVisitReview.__table__.columns
    assert "next_followup_at" in SiteVisitReview.__table__.columns
    assert "followup_id" in SiteVisitReview.__table__.columns
    assert "batch_key" in SiteVisitReview.__table__.columns
