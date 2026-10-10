from datetime import datetime

from starlette.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.routers.lead_visit_monitoring as routes
from app.models import Customer, FollowUp, SiteVisit, User


def _request(query=b""):
    path = "/admin/lead-monitoring/calendar"
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
    })


def _user(db, username, role):
    user = User(
        username=username,
        password_hash="test-hash",
        role=role,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    return user


def test_calendar_filters_followups_and_visits_by_date_and_caller(db_session, monkeypatch):
    admin = _user(db_session, "admin-calendar", "ADMIN")
    caller_one = _user(db_session, "caller-calendar-one", "TELECALLER")
    caller_two = _user(db_session, "caller-calendar-two", "SALES_EXECUTIVE")
    customer_one = Customer(name="Matching Customer", mobile="9000000001")
    customer_two = Customer(name="Excluded Customer", mobile="9000000002")
    db_session.add_all([customer_one, customer_two])
    db_session.flush()

    db_session.add_all([
        FollowUp(
            customer_id=customer_one.id,
            assigned_user_id=caller_one.id,
            due_at=datetime(2026, 10, 10, 10, 0),
            purpose="Matching follow-up",
            completed=False,
        ),
        FollowUp(
            customer_id=customer_two.id,
            assigned_user_id=caller_two.id,
            due_at=datetime(2026, 10, 11, 10, 0),
            purpose="Excluded follow-up",
            completed=False,
        ),
        SiteVisit(
            customer_id=customer_one.id,
            sales_employee_id=caller_one.id,
            scheduled_at=datetime(2026, 10, 10, 14, 0),
            status="SCHEDULED",
        ),
        SiteVisit(
            customer_id=customer_two.id,
            sales_employee_id=caller_two.id,
            scheduled_at=datetime(2026, 10, 11, 14, 0),
            status="SCHEDULED",
        ),
    ])
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.calendar_dashboard(
        _request(b"start_date=2026-10-10&end_date=2026-10-10&caller_id=" + str(caller_one.id).encode()),
        db_session,
    )

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 200
    assert "Matching follow-up" in response.body.decode()
    assert "Matching Customer" in response.body.decode()
    assert "Excluded Customer" not in response.body.decode()
    assert "Excluded follow-up" not in response.body.decode()


def test_calendar_rejects_non_manager_roles(db_session, monkeypatch):
    caller = _user(db_session, "caller-calendar-unauthorized", "TELECALLER")
    monkeypatch.setattr(routes, "_actor", lambda request, db: caller)

    response = routes.calendar_dashboard(_request(), db_session)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_calendar_invalid_filters_show_warning_without_crashing(db_session, monkeypatch):
    admin = _user(db_session, "admin-calendar-invalid", "ADMIN")
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.calendar_dashboard(
        _request(b"start_date=not-a-date&caller_id=not-a-user"),
        db_session,
    )

    assert isinstance(response, HTMLResponse)
    body = response.body.decode()
    assert response.status_code == 200
    assert "Start date is invalid" in body
    assert "Caller filter is invalid" in body
