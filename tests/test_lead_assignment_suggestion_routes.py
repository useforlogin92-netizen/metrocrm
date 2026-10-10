"""Route-level regression tests for manager-approved lead assignment."""
from starlette.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.routers.lead_assignment_suggestions as routes
from app.models import AuditEvent, Customer, Lead, LeadAssignmentHistory, User


def _request(path="/admin/lead-assignment-suggestions/approve"):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
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
        is_active=True,
        is_approved=True,
        **kwargs,
    )
    db.add(user)
    db.flush()
    return user


def test_unauthorized_role_cannot_approve_assignment(db_session, monkeypatch):
    caller = _user(db_session, "caller1", "SALES_EXECUTIVE")
    lead = Lead(source="manual", status="NEW", assigned_user_id=caller.id)
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: caller)

    response = routes.approve_assignment(
        _request(), lead_id=lead.id, assigned_user_id=caller.id,
        reason="test", db=db_session,
    )

    assert isinstance(response, RedirectResponse)
    db_session.refresh(lead)
    assert lead.assigned_user_id == caller.id
    assert db_session.query(LeadAssignmentHistory).count() == 0
    assert db_session.query(AuditEvent).filter_by(action="LEAD_ASSIGNMENT_APPROVED").count() == 0


def test_admin_approval_persists_owner_history_and_audit(db_session, monkeypatch):
    admin = _user(db_session, "admin1", "ADMIN")
    old_owner = _user(db_session, "caller-old", "SALES_EXECUTIVE")
    new_owner = _user(db_session, "caller-new", "TELECALLER")
    customer = Customer(name="Test Customer", mobile="9000000001")
    db_session.add(customer)
    db_session.flush()
    lead = Lead(
        customer_id=customer.id, source="WhatsApp", status="NEW",
        assigned_user_id=old_owner.id,
    )
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.approve_assignment(
        _request(), lead_id=lead.id, assigned_user_id=new_owner.id,
        reason="Balanced workload", db=db_session,
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    db_session.refresh(lead)
    assert lead.assigned_user_id == new_owner.id
    assert lead.original_owner_id == new_owner.id
    history = db_session.query(LeadAssignmentHistory).filter_by(lead_id=lead.id).one()
    assert history.from_user_id == old_owner.id
    assert history.to_user_id == new_owner.id
    assert history.assigned_by_id == admin.id
    assert history.reason == "Balanced workload"
    event = db_session.query(AuditEvent).filter_by(action="LEAD_ASSIGNMENT_APPROVED").one()
    assert event.actor_user_id == admin.id
    assert event.entity_id == str(lead.id)


def test_admin_cannot_assign_to_inactive_or_ineligible_user(db_session, monkeypatch):
    admin = _user(db_session, "admin2", "ADMIN")
    inactive = _user(db_session, "inactive-caller", "SALES_EXECUTIVE", is_active=False)
    current = _user(db_session, "caller-current", "SALES_EXECUTIVE")
    lead = Lead(source="manual", status="NEW", assigned_user_id=current.id)
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.approve_assignment(
        _request(), lead_id=lead.id, assigned_user_id=inactive.id,
        reason="Should be rejected", db=db_session,
    )

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 403
    db_session.refresh(lead)
    assert lead.assigned_user_id == current.id
    assert db_session.query(LeadAssignmentHistory).count() == 0
