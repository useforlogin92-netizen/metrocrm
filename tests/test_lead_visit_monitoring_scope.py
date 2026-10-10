from app.models import Lead, User
from app.routers.lead_visit_monitoring import _lead_in_scope, _scope_user_ids


def test_manager_monitoring_scope_includes_reporting_tree_but_excludes_other_team(db_session):
    manager = User(username="monitor-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    team_lead = User(username="monitor-tl", password_hash="x", role="TL", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    db_session.add(team_lead)
    db_session.flush()
    executive = User(username="monitor-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=team_lead.id, is_active=True, is_approved=True)
    outsider = User(username="monitor-outsider", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([executive, outsider])
    db_session.flush()
    team_lead_row = Lead(source="WEBSITE", status="NEW", assigned_user_id=executive.id)
    outsider_row = Lead(source="WEBSITE", status="NEW", assigned_user_id=outsider.id)
    db_session.add_all([team_lead_row, outsider_row])
    db_session.commit()

    scope = _scope_user_ids(manager, db_session)
    assert scope == {manager.id, team_lead.id, executive.id}
    assert _lead_in_scope(manager, team_lead_row, db_session)
    assert not _lead_in_scope(manager, outsider_row, db_session)


def test_team_lead_scope_includes_its_descendants_only(db_session):
    team_lead = User(username="monitor-tl-two", password_hash="x", role="TL", is_active=True, is_approved=True)
    db_session.add(team_lead)
    db_session.flush()
    caller = User(username="monitor-caller", password_hash="x", role="TELECALLER", reporting_manager_id=team_lead.id, is_active=True, is_approved=True)
    outside = User(username="monitor-outside-two", password_hash="x", role="TELECALLER", is_active=True, is_approved=True)
    db_session.add_all([caller, outside])
    db_session.flush()
    assigned = Lead(source="REFERRAL", status="NEW", assigned_user_id=caller.id)
    unrelated = Lead(source="REFERRAL", status="NEW", assigned_user_id=outside.id)
    db_session.add_all([assigned, unrelated])
    db_session.commit()

    assert _lead_in_scope(team_lead, assigned, db_session)
    assert not _lead_in_scope(team_lead, unrelated, db_session)



def test_sales_executive_monitoring_scope_is_only_their_own_user_id(db_session):
    from app.routers.lead_visit_monitoring import _can_reassign

    executive = User(username="monitor-own-only", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add(executive)
    db_session.flush()
    child = User(username="monitor-child", password_hash="x", role="TELECALLER", reporting_manager_id=executive.id, is_active=True, is_approved=True)
    db_session.add(child)
    db_session.commit()

    assert _scope_user_ids(executive, db_session) == {executive.id}
    assert not _can_reassign(executive)
    manager = User(username="monitor-manager-assign", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    assert _can_reassign(manager)



def test_sales_executive_monitoring_includes_visits_reassigned_to_them(db_session, monkeypatch):
    from datetime import datetime
    from starlette.requests import Request
    from app.models import Customer, Developer, Project, SiteVisit
    from app.routers import lead_visit_monitoring as monitoring

    visit_owner = User(username="monitor-backup-owner", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    lead_owner = User(username="monitor-original-owner", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Monitoring Reassigned Customer", mobile="9876500666")
    developer = Developer(name="Monitoring Developer")
    db_session.add_all([visit_owner, lead_owner, customer, developer])
    db_session.flush()
    project = Project(developer_id=developer.id, name="Monitoring Residency", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="SITE_VISIT_SCHEDULED", assigned_user_id=lead_owner.id)
    db_session.add(lead)
    db_session.flush()
    visit = SiteVisit(customer_id=customer.id, lead_id=lead.id, project_id=project.id,
                      sales_employee_id=visit_owner.id, conducted_by_id=visit_owner.id,
                      scheduled_at=datetime(2026, 10, 12, 12, 0), status="SCHEDULED")
    db_session.add(visit)
    db_session.commit()

    request = Request({"type": "http", "method": "GET", "path": "/admin/lead-monitoring", "headers": [], "query_string": b"", "session": {}})
    monkeypatch.setattr(monitoring, "_actor", lambda request, db: visit_owner)
    monkeypatch.setattr(monitoring, "csrf_token", lambda request: "test-csrf")

    response = monitoring.dashboard(request, db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "My site visits" in html
    assert "Monitoring Reassigned Customer" in html
