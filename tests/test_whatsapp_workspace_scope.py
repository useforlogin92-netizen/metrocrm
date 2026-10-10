from fastapi import HTTPException
from starlette.requests import Request

from app.models import Customer, Developer, Lead, Project, Unit, User
from app.routers import whatsapp


def _request(path="/whatsapp", method="GET"):
    return Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""})


def test_whatsapp_workspace_lists_only_assigned_leads_and_available_inventory(db_session, monkeypatch):
    actor = User(username="whatsapp-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    other = User(username="whatsapp-other", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    own_customer = Customer(name="WhatsApp Assigned Customer", mobile="9876500011")
    other_customer = Customer(name="WhatsApp Other Customer", mobile="9876500022")
    developer = Developer(name="WhatsApp Test Developer")
    db_session.add_all([actor, other, own_customer, other_customer, developer])
    db_session.flush()
    own_lead = Lead(customer_id=own_customer.id, source="WEBSITE", status="NEW", assigned_user_id=actor.id)
    other_lead = Lead(customer_id=other_customer.id, source="REFERRAL", status="NEW", assigned_user_id=other.id)
    db_session.add_all([own_lead, other_lead])
    db_session.flush()
    project = Project(developer_id=developer.id, name="WhatsApp Test Residency", city="Mumbai", locality="Borivali")
    db_session.add(project)
    db_session.flush()
    available = Unit(project_id=project.id, unit_number="A-101", bhk="2 BHK", property_type="Apartment", status="AVAILABLE", price=8000000)
    sold = Unit(project_id=project.id, unit_number="A-102", bhk="2 BHK", property_type="Apartment", status="SOLD", price=8200000)
    db_session.add_all([available, sold])
    db_session.commit()

    monkeypatch.setattr(whatsapp, "_user", lambda request, db: actor)
    monkeypatch.setattr(whatsapp, "csrf_token", lambda request: "test-csrf")
    response = whatsapp.whatsapp_page(_request(), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "WhatsApp Assigned Customer" in html
    assert "WhatsApp Other Customer" not in html
    assert "A-101" in html
    assert "A-102" not in html
    assert f'value="{own_lead.id}"' in html


def test_whatsapp_property_share_rejects_sold_inventory(db_session, monkeypatch):
    actor = User(username="whatsapp-sold-check", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Sold Property Customer", mobile="9876500033")
    developer = Developer(name="Sold Property Developer")
    db_session.add_all([actor, customer, developer])
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="NEW", assigned_user_id=actor.id)
    db_session.add(lead)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Sold Property Residency", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    sold = Unit(project_id=project.id, unit_number="S-101", status="SOLD")
    db_session.add(sold)
    db_session.commit()

    monkeypatch.setattr(whatsapp, "_user", lambda request, db: actor)

    try:
        whatsapp.share_property_whatsapp(_request("/whatsapp/property-share", "POST"), lead.id, sold.id, project.id, db_session)
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == "property_unavailable"
    else:
        raise AssertionError("Sold inventory must not be shareable")
