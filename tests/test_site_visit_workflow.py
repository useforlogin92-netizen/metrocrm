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



def test_sales_executive_staff_scope_excludes_unrelated_users(db_session):
    from app.models import User
    from app.routers.site_visit_workflow import _staff_visible_to

    actor = User(username="scope-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    teammate = User(username="scope-exec-other", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([actor, teammate])
    db_session.flush()

    assert _staff_visible_to(actor, actor, db_session)
    assert not _staff_visible_to(actor, teammate, db_session)


def test_manager_staff_scope_allows_reporting_tree_only(db_session):
    from app.models import User
    from app.routers.site_visit_workflow import _staff_visible_to

    manager = User(username="scope-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    team_member = User(username="scope-member", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    outsider = User(username="scope-outsider", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([team_member, outsider])
    db_session.flush()

    assert _staff_visible_to(manager, team_member, db_session)
    assert not _staff_visible_to(manager, outsider, db_session)


def test_inactive_staff_is_never_selectable_for_site_visit(db_session):
    from app.models import User
    from app.routers.site_visit_workflow import _staff_visible_to

    admin = User(username="scope-admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    inactive = User(username="scope-inactive", password_hash="x", role="SALES_EXECUTIVE", is_active=False, is_approved=True)
    db_session.add_all([admin, inactive])
    db_session.flush()

    assert not _staff_visible_to(admin, inactive, db_session)



def _visit_request(path, method="GET"):
    from starlette.requests import Request
    return Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b"", "session": {}})


def test_manager_can_open_and_save_feedback_for_reporting_tree_visit(db_session, monkeypatch):
    from datetime import datetime
    from app.models import Customer, Developer, Lead, Project, SiteVisit, User
    from app.routers import site_visit_workflow as workflow
    from app.site_visit_workflow_models import SiteVisitReview

    manager = User(username="feedback-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    executive = User(username="feedback-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    customer = Customer(name="Feedback Customer", mobile="9876500999")
    developer = Developer(name="Feedback Developer")
    db_session.add_all([executive, customer, developer])
    db_session.flush()
    project = Project(developer_id=developer.id, name="Feedback Residency", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="SITE_VISIT_SCHEDULED", assigned_user_id=executive.id)
    db_session.add(lead)
    db_session.flush()
    visit = SiteVisit(customer_id=customer.id, lead_id=lead.id, project_id=project.id,
                      sales_employee_id=executive.id, conducted_by_id=executive.id,
                      scheduled_at=datetime(2026, 10, 12, 10, 0), status="SCHEDULED")
    db_session.add(visit)
    db_session.commit()

    monkeypatch.setattr(workflow, "_actor", lambda request, db: manager)
    monkeypatch.setattr(workflow, "csrf_token", lambda request: "test-csrf")
    page = workflow.visit_feedback_page(visit.id, _visit_request(f"/site-visits/{visit.id}/feedback"), db_session)
    assert page.status_code == 200
    assert "Feedback Customer" in page.body.decode()

    monkeypatch.setattr(workflow, "require_csrf", lambda request, token: None)
    response = workflow.save_visit_feedback(
        visit_id=visit.id, request=_visit_request(f"/site-visits/{visit.id}/feedback", "POST"),
        status="COMPLETED", interest_level="HOT", deal_status="FOLLOW_UP_REQUIRED",
        quoted_price="", customer_feedback="Customer liked the property",
        customer_objections="", next_followup_at="", next_followup_plan="Call tomorrow",
        other_project_required="no", next_project_id=None, csrf_token_value="test-csrf", db=db_session,
    )
    db_session.refresh(visit)
    review = db_session.query(SiteVisitReview).filter_by(visit_id=visit.id).one()
    assert response.status_code == 303
    assert visit.status == "COMPLETED"
    assert review.customer_feedback == "Customer liked the property"
    assert review.updated_by_id == manager.id


def test_site_visit_created_from_assigned_lead_keeps_sales_owner(db_session, monkeypatch):
    from datetime import datetime
    from app.models import Customer, Developer, Lead, Project, SiteVisit, User
    from app.routers import site_visit_workflow as workflow

    executive = User(username="visit-owner-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Visit Owner Customer", mobile="9876500888")
    developer = Developer(name="Visit Owner Developer")
    db_session.add_all([executive, customer, developer])
    db_session.flush()
    project = Project(developer_id=developer.id, name="Visit Owner Residency", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="QUALIFIED", assigned_user_id=executive.id)
    db_session.add(lead)
    db_session.commit()

    monkeypatch.setattr(workflow, "_actor", lambda request, db: executive)
    monkeypatch.setattr(workflow, "require_csrf", lambda request, token: None)
    response = workflow.create_visit_batch(
        request=_visit_request("/site-visits/create", "POST"), lead_id=lead.id,
        scheduled_at="2026-10-12T10:00", called_by_id=executive.id, conducted_by_id=executive.id,
        developer_sm_name="", developer_sm_phone="", project_ids=[project.id], notes="",
        csrf_token_value="test-csrf", db=db_session,
    )
    visit = db_session.query(SiteVisit).filter_by(lead_id=lead.id, project_id=project.id).one()
    assert response.status_code == 303
    assert visit.sales_employee_id == executive.id



def test_reassigned_sales_executive_can_open_and_update_their_visit_feedback(db_session, monkeypatch):
    from datetime import datetime
    from app.models import Customer, Developer, Lead, Project, SiteVisit, User
    from app.routers import site_visit_workflow as workflow

    visit_owner = User(username="backup-visit-owner", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    lead_owner = User(username="original-lead-owner", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Reassigned Visit Customer", mobile="9876500777")
    developer = Developer(name="Reassigned Visit Developer")
    db_session.add_all([visit_owner, lead_owner, customer, developer])
    db_session.flush()
    project = Project(developer_id=developer.id, name="Reassigned Visit Residency", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="SITE_VISIT_SCHEDULED", assigned_user_id=lead_owner.id)
    db_session.add(lead)
    db_session.flush()
    visit = SiteVisit(customer_id=customer.id, lead_id=lead.id, project_id=project.id,
                      sales_employee_id=visit_owner.id, conducted_by_id=visit_owner.id,
                      scheduled_at=datetime(2026, 10, 12, 11, 0), status="SCHEDULED")
    db_session.add(visit)
    db_session.commit()

    monkeypatch.setattr(workflow, "_actor", lambda request, db: visit_owner)
    monkeypatch.setattr(workflow, "csrf_token", lambda request: "test-csrf")
    page = workflow.visit_feedback_page(visit.id, _visit_request(f"/site-visits/{visit.id}/feedback"), db_session)
    assert page.status_code == 200
    assert "Reassigned Visit Customer" in page.body.decode()

    monkeypatch.setattr(workflow, "require_csrf", lambda request, token: None)
    response = workflow.save_visit_feedback(
        visit_id=visit.id, request=_visit_request(f"/site-visits/{visit.id}/feedback", "POST"),
        status="COMPLETED", interest_level="WARM", deal_status="FOLLOW_UP_REQUIRED",
        quoted_price="", customer_feedback="Backup caller completed the visit",
        customer_objections="", next_followup_at="2026-10-13T10:00", next_followup_plan="Call customer",
        other_project_required="no", next_project_id=None, csrf_token_value="test-csrf", db=db_session,
    )
    from app.models import FollowUp
    db_session.refresh(visit)
    followup = db_session.query(FollowUp).filter_by(lead_id=lead.id).one()
    assert response.status_code == 303
    assert visit.status == "COMPLETED"
    assert followup.assigned_user_id == visit_owner.id
