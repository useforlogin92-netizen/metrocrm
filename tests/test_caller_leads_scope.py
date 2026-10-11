from starlette.requests import Request

from app.models import Customer, Lead, User
from app.routers import caller_leads


def _request():
    return Request({"type": "http", "method": "GET", "path": "/caller/leads", "headers": [], "query_string": b"", "session": {}})


def test_manager_lead_workspace_includes_reporting_tree_only(db_session, monkeypatch):
    manager = User(username="lead-scope-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    team_lead = User(username="lead-scope-tl", password_hash="x", role="TL", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    db_session.add(team_lead)
    db_session.flush()
    executive = User(username="lead-scope-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=team_lead.id, is_active=True, is_approved=True)
    outsider = User(username="lead-scope-outsider", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    own_customer = Customer(name="Manager Own Customer")
    team_customer = Customer(name="Manager Team Customer")
    outside_customer = Customer(name="Outside Team Customer")
    db_session.add_all([executive, outsider, own_customer, team_customer, outside_customer])
    db_session.flush()
    own_lead = Lead(customer_id=own_customer.id, source="WEBSITE", status="NEW", assigned_user_id=manager.id)
    team_lead_record = Lead(customer_id=team_customer.id, source="REFERRAL", status="NEW", assigned_user_id=executive.id)
    outside_lead = Lead(customer_id=outside_customer.id, source="WEBSITE", status="NEW", assigned_user_id=outsider.id)
    db_session.add_all([own_lead, team_lead_record, outside_lead])
    db_session.commit()
    monkeypatch.setattr(caller_leads, "current_user", lambda request, db: manager)

    response = caller_leads.caller_leads(_request(), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "Manager Own Customer" in html
    assert "Manager Team Customer" in html
    assert "Outside Team Customer" not in html
    assert "Assign Caller" in html
    assert "/caller/leads/" in html and "/assign" in html
    assert "lead-scope-exec" in html


def test_sales_executive_lead_workspace_shows_only_own_assigned_leads(db_session, monkeypatch):
    executive = User(username="lead-scope-own-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    other = User(username="lead-scope-other-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    own_customer = Customer(name="Executive Own Customer")
    other_customer = Customer(name="Executive Other Customer")
    db_session.add_all([executive, other, own_customer, other_customer])
    db_session.flush()
    db_session.add_all([
        Lead(customer_id=own_customer.id, source="WEBSITE", status="NEW", assigned_user_id=executive.id),
        Lead(customer_id=other_customer.id, source="REFERRAL", status="NEW", assigned_user_id=other.id),
    ])
    db_session.commit()
    monkeypatch.setattr(caller_leads, "current_user", lambda request, db: executive)

    response = caller_leads.caller_leads(_request(), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "Executive Own Customer" in html
    assert "Executive Other Customer" not in html
