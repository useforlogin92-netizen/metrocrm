from pathlib import Path

from starlette.requests import Request

from app.models import AuditEvent, Customer, Lead, User
from app.routers import caller_leads


def _request(path="/caller/leads/quick-add", method="POST"):
    return Request({
        "type": "http", "method": method, "path": path, "headers": [],
        "query_string": b"", "session": {},
    })


def test_quick_add_route_is_registered_and_csrf_protected():
    from app.main import app
    import inspect

    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/caller/leads/quick-add"
        and "POST" in (getattr(route, "methods", None) or set())
    )
    assert route.endpoint.__name__ == "quick_add_caller_lead"
    assert "csrf_token" in Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    assert "Depends(require_csrf)" in inspect.getsource(route.endpoint)


def test_quick_add_creates_customer_and_assigns_lead_to_current_caller(db_session, monkeypatch):
    actor = User(
        username="quick-add-exec", password_hash="x", role="SALES_EXECUTIVE",
        is_active=True, is_approved=True,
    )
    db_session.add(actor)
    db_session.commit()
    monkeypatch.setattr(caller_leads, "current_user", lambda request, db: actor)

    response = caller_leads.quick_add_caller_lead(
        request=_request(), name="Walk-in Customer", mobile="98765 43210",
        source="WALK_IN", email="walkin@example.com",
        preferred_location="Borivali West", bhk="2 BHK",
        budget_min="5000000", budget_max="8500000",
        requirement="Ready possession", notes="Visited office",
        _csrf=None, db=db_session,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard?lead_created=1"
    customer = db_session.query(Customer).filter_by(name="Walk-in Customer").one()
    lead = db_session.query(Lead).filter_by(customer_id=customer.id).one()
    event = db_session.query(AuditEvent).filter_by(entity_id=str(lead.id)).one()
    assert customer.mobile == "98765 43210"
    assert customer.email == "walkin@example.com"
    assert lead.source == "WALK_IN"
    assert lead.status == "NEW"
    assert lead.assigned_user_id == actor.id
    assert lead.original_owner_id == actor.id
    assert lead.preferred_location == "Borivali West"
    assert str(lead.budget_min) == "5000000.00"
    assert event.action == "CALLER_QUICK_LEAD_CREATED"


def test_quick_add_rejects_invalid_budget_without_creating_customer(db_session, monkeypatch):
    actor = User(
        username="quick-add-invalid", password_hash="x", role="TELECALLER",
        is_active=True, is_approved=True,
    )
    db_session.add(actor)
    db_session.commit()
    monkeypatch.setattr(caller_leads, "current_user", lambda request, db: actor)

    response = caller_leads.quick_add_caller_lead(
        request=_request(), name="Invalid Budget Customer", mobile="9876543210",
        source="INCOMING_CALL", email="", preferred_location="", bhk="",
        budget_min="9000000", budget_max="4000000", requirement="", notes="",
        _csrf=None, db=db_session,
    )

    assert response.status_code == 400
    assert db_session.query(Customer).filter_by(name="Invalid Budget Customer").count() == 0
    assert db_session.query(Lead).count() == 0


def test_dashboard_template_includes_live_metrics_followups_and_honest_offline_state():
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    main_source = Path("app/main.py").read_text(encoding="utf-8")

    for label in (
        "TODAY'S LEADS", "PENDING FOLLOW-UPS", "SITE VISITS SCHEDULED",
        "CLOSED DEALS", "Today's Priority Follow-ups", "Quick Add Lead",
        "Offline CRM sync: not enabled",
    ):
        assert label in template
    assert "select(func.count(Lead.id))" in main_source
    assert "select(func.count(FollowUp.id))" in main_source
    assert "select(func.count(SiteVisit.id))" in main_source
    assert "select(func.count(Booking.id))" in main_source
    assert "navigator.onLine" in template
