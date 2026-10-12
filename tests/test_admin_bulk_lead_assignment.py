"""Regression tests for Admin/Super Admin bulk lead assignment."""
from starlette.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.routers.admin_bulk_lead_assignment as routes
from app.models import AuditEvent, Customer, Lead, LeadAssignmentHistory, User


def _request(path="/admin/all-leads/bulk-assign", method="POST"):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
    })


def _user(db, username, role, **kwargs):
    user = User(
        username=username,
        password_hash="test-hash",
        role=role,
        is_active=kwargs.pop("is_active", True),
        is_approved=kwargs.pop("is_approved", True),
        **kwargs,
    )
    db.add(user)
    db.flush()
    return user


def test_bulk_assignment_updates_selected_leads_and_records_history(db_session, monkeypatch):
    admin = _user(db_session, "admin-bulk", "ADMIN")
    old_owner = _user(db_session, "caller-old-bulk", "TELECALLER")
    new_owner = _user(db_session, "caller-new-bulk", "SALES_EXECUTIVE")
    customer = Customer(name="Bulk Lead Customer", mobile="9876543210")
    db_session.add(customer)
    db_session.flush()
    first = Lead(customer_id=customer.id, source="manual", status="NEW", assigned_user_id=old_owner.id)
    second = Lead(source="website", status="NEW")
    db_session.add_all([first, second])
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.bulk_assign(
        _request(), lead_ids=[first.id, second.id, first.id],
        assigned_user_id=new_owner.id, reason="New caller allocation", db=db_session,
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.assigned_user_id == new_owner.id
    assert second.assigned_user_id == new_owner.id
    history = db_session.query(LeadAssignmentHistory).order_by(LeadAssignmentHistory.lead_id).all()
    assert len(history) == 2
    assert history[0].from_user_id == old_owner.id
    assert history[0].to_user_id == new_owner.id
    assert history[0].assigned_by_id == admin.id
    assert history[0].reason == "New caller allocation"
    assert db_session.query(AuditEvent).filter_by(action="LEADS_BULK_ASSIGNED").count() == 2


def test_bulk_assignment_rejects_non_admin_without_mutating_leads(db_session, monkeypatch):
    caller = _user(db_session, "caller-not-admin", "TELECALLER")
    target = _user(db_session, "target-caller", "SALES_EXECUTIVE")
    lead = Lead(source="manual", status="NEW")
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: caller)

    response = routes.bulk_assign(
        _request(), lead_ids=[lead.id], assigned_user_id=target.id,
        reason="Not allowed", db=db_session,
    )

    assert isinstance(response, RedirectResponse)
    db_session.refresh(lead)
    assert lead.assigned_user_id is None
    assert db_session.query(LeadAssignmentHistory).count() == 0


def test_bulk_assignment_rejects_inactive_or_non_caller_target(db_session, monkeypatch):
    admin = _user(db_session, "admin-ineligible", "SUPER_ADMIN")
    inactive = _user(db_session, "inactive-bulk-target", "TELECALLER", is_active=False)
    lead = Lead(source="manual", status="NEW")
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.bulk_assign(
        _request(), lead_ids=[lead.id], assigned_user_id=inactive.id,
        reason="Invalid target", db=db_session,
    )

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 422
    db_session.refresh(lead)
    assert lead.assigned_user_id is None
    assert db_session.query(LeadAssignmentHistory).count() == 0


def test_all_leads_and_history_routes_are_registered():
    from app.main import app

    routes_found = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/admin/all-leads", "GET") in routes_found
    assert ("/admin/all-leads/bulk-assign", "POST") in routes_found
    assert ("/admin/all-leads/history", "GET") in routes_found
