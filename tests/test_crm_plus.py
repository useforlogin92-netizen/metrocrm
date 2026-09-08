from datetime import datetime, timezone

from app.crm_plus_models import CRMTask, LeadScore, SalesTarget
from app.models import Lead, User
from app.routers.crm_plus import score_lead, team_ids


def test_lead_score_rewards_complete_fresh_lead(db_session):
    user = User(username="score_user", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add(user)
    db_session.flush()
    lead = Lead(source="WHATSAPP", status="NEW", assigned_user_id=user.id, budget_min=5000000, budget_max=10000000, preferred_location="Thane", bhk="2 BHK", property_type="APARTMENT", created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add(lead)
    db_session.commit()
    score, grade, reasons = score_lead(lead)
    assert score >= 75
    assert grade == "A"
    assert "fresh lead" in reasons


def test_team_scope_for_manager_includes_reporting_tree(db_session):
    manager = User(username="mgr_plus", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    tl = User(username="tl_plus", password_hash="x", role="TL", is_active=True, is_approved=True)
    rep = User(username="rep_plus", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    outsider = User(username="out_plus", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([manager, tl, rep, outsider])
    db_session.flush()
    tl.reporting_manager_id = manager.id
    rep.reporting_manager_id = tl.id
    db_session.commit()
    assert team_ids(manager, db_session) == {manager.id, tl.id, rep.id}
    assert outsider.id not in team_ids(manager, db_session)


def test_super_admin_scope_is_global(db_session):
    admin = User(username="sa_plus", password_hash="x", role="SUPER_ADMIN", is_active=True, is_approved=True)
    other = User(username="staff_plus", password_hash="x", role="TELECALLER", is_active=True, is_approved=True)
    db_session.add_all([admin, other])
    db_session.commit()
    assert team_ids(admin, db_session) == {admin.id, other.id}


def test_advanced_models_have_expected_relationship_keys():
    assert "lead_id" in CRMTask.__table__.columns
    assert "lead_id" in LeadScore.__table__.columns
    assert "sales_target" in SalesTarget.__table__.columns
