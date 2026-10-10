from app.models import Lead, User
from app.routers.email import _visible_leads


def test_sales_executive_email_workspace_lists_only_assigned_leads(db_session):
    executive = User(username="email-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    other = User(username="email-other", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([executive, other])
    db_session.flush()
    own = Lead(source="WEBSITE", status="NEW", assigned_user_id=executive.id)
    outside = Lead(source="REFERRAL", status="NEW", assigned_user_id=other.id)
    db_session.add_all([own, outside])
    db_session.commit()

    visible = _visible_leads(executive, db_session)

    assert [lead.id for lead in visible] == [own.id]
    assert outside.id not in {lead.id for lead in visible}


def test_team_lead_email_workspace_lists_reporting_tree_only(db_session):
    manager = User(username="email-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    team_lead = User(username="email-tl", password_hash="x", role="TL", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    db_session.add(team_lead)
    db_session.flush()
    executive = User(username="email-team-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=team_lead.id, is_active=True, is_approved=True)
    outsider = User(username="email-outsider", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([executive, outsider])
    db_session.flush()
    team_lead_record = Lead(source="WEBSITE", status="NEW", assigned_user_id=executive.id)
    outside_record = Lead(source="REFERRAL", status="NEW", assigned_user_id=outsider.id)
    db_session.add_all([team_lead_record, outside_record])
    db_session.commit()

    visible = _visible_leads(manager, db_session)

    assert {lead.id for lead in visible} == {team_lead_record.id}


def test_admin_email_workspace_can_list_all_leads(db_session):
    admin = User(username="email-admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    employee = User(username="email-employee", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([admin, employee])
    db_session.flush()
    record = Lead(source="WEBSITE", status="NEW", assigned_user_id=employee.id)
    db_session.add(record)
    db_session.commit()

    assert record.id in {lead.id for lead in _visible_leads(admin, db_session)}



def test_email_workspace_route_lists_only_the_sales_executives_assigned_customer(db_session, monkeypatch):
    from starlette.requests import Request
    from app.models import Customer
    from app.routers import email

    executive = User(username="email-page-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    other = User(username="email-page-other", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    own_customer = Customer(name="Assigned Customer", email="assigned@example.com")
    other_customer = Customer(name="Other Customer", email="other@example.com")
    db_session.add_all([executive, other, own_customer, other_customer])
    db_session.flush()
    own_lead = Lead(customer_id=own_customer.id, source="WEBSITE", status="NEW", assigned_user_id=executive.id)
    other_lead = Lead(customer_id=other_customer.id, source="REFERRAL", status="NEW", assigned_user_id=other.id)
    db_session.add_all([own_lead, other_lead])
    db_session.commit()

    request = Request({"type": "http", "method": "GET", "path": "/email", "headers": [], "query_string": b""})
    monkeypatch.setattr(email, "_user", lambda request, db: executive)

    response = email.email_workspace(request, db_session)

    assert response.status_code == 200
    assert "Assigned Customer" in response.body.decode()
    assert "Other Customer" not in response.body.decode()
    assert f"/caller/lead/{own_lead.id}/call" in response.body.decode()


def test_email_workspace_get_route_is_registered_on_live_app():
    from app.main_portal import app

    routes = {(getattr(route, "path", None), tuple(sorted(getattr(route, "methods", set()) or set()))) for route in app.routes}
    assert ("/email", ("GET",)) in routes
    assert ("/email/property-share", ("POST",)) in routes
