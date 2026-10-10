from types import SimpleNamespace

from app.routers.site_visit_workflow import _visible_lead
from app.site_visit_workflow_models import SiteVisitReview


def test_admin_and_super_admin_can_manage_any_lead_visit():
    lead = SimpleNamespace(assigned_user_id=900)
    assert _visible_lead(SimpleNamespace(role="SUPER_ADMIN", id=1), lead)
    assert _visible_lead(SimpleNamespace(role="ADMIN", id=2), lead)


def test_sales_executive_can_only_manage_visits_for_assigned_lead():
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



def test_manager_can_manage_visit_for_reporting_tree_member(db_session):
    from app.models import Lead, User

    manager = User(username="visit-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    team_lead = User(username="visit-tl", password_hash="x", role="TL", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    db_session.add(team_lead)
    db_session.flush()
    executive = User(username="visit-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=team_lead.id, is_active=True, is_approved=True)
    outsider = User(username="visit-outsider", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([executive, outsider])
    db_session.flush()
    team_lead_lead = Lead(source="WEBSITE", status="NEW", assigned_user_id=executive.id)
    outside_lead = Lead(source="WEBSITE", status="NEW", assigned_user_id=outsider.id)
    db_session.add_all([team_lead_lead, outside_lead])
    db_session.commit()

    assert _visible_lead(manager, team_lead_lead, db_session)
    assert not _visible_lead(manager, outside_lead, db_session)
