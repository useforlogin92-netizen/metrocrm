from datetime import datetime

from starlette.requests import Request

from app.models import Customer, FollowUp, SiteVisit, User
from app.routers.lead_visit_monitoring import (
    _site_visits_in_scope_query,
    _visit_in_scope,
    calendar_dashboard,
)
from fastapi.responses import HTMLResponse, RedirectResponse


def _user(db, username: str, role: str, manager_id: int | None = None) -> User:
    user = User(
        username=username,
        password_hash="test-hash",
        role=role,
        is_active=True,
        is_approved=True,
        reporting_manager_id=manager_id,
    )
    db.add(user)
    db.flush()
    return user


def _calendar_request(query: bytes = b"") -> Request:
    path = "/admin/lead-monitoring/calendar"
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
        "session": {},
    })


def test_scoped_monitoring_includes_assigned_visit_without_linked_lead(db_session):
    caller = _user(db_session, "unlinked-scope-caller", "TELECALLER")
    other = _user(db_session, "unlinked-scope-other", "TELECALLER")
    assigned = SiteVisit(
        lead_id=None,
        sales_employee_id=caller.id,
        scheduled_at=datetime(2026, 10, 12, 10, 0),
        status="SCHEDULED",
    )
    excluded = SiteVisit(
        lead_id=None,
        sales_employee_id=other.id,
        scheduled_at=datetime(2026, 10, 12, 11, 0),
        status="SCHEDULED",
    )
    db_session.add_all([assigned, excluded])
    db_session.flush()

    visits = db_session.scalars(_site_visits_in_scope_query({caller.id})).all()

    assert [visit.id for visit in visits] == [assigned.id]


def test_unlinked_visit_scope_allows_admin_and_assigned_team_but_not_other_team(db_session):
    admin = _user(db_session, "unlinked-scope-admin", "ADMIN")
    manager = _user(db_session, "unlinked-scope-manager", "MANAGER")
    teammate = _user(db_session, "unlinked-scope-teammate", "TELECALLER", manager.id)
    outsider = _user(db_session, "unlinked-scope-outsider", "TELECALLER")
    visit = SiteVisit(
        lead_id=None,
        sales_employee_id=teammate.id,
        scheduled_at=datetime(2026, 10, 12, 10, 0),
        status="SCHEDULED",
    )

    assert _visit_in_scope(admin, visit, None, db_session)
    assert _visit_in_scope(manager, visit, None, db_session)
    visit.sales_employee_id = outsider.id
    assert not _visit_in_scope(manager, visit, None, db_session)


def test_monitoring_calendar_filters_date_and_caller(db_session, monkeypatch):
    import app.routers.lead_visit_monitoring as routes

    admin = _user(db_session, "calendar-admin-regression", "ADMIN")
    caller_one = _user(db_session, "calendar-caller-regression-one", "TELECALLER")
    caller_two = _user(db_session, "calendar-caller-regression-two", "SALES_EXECUTIVE")
    customer_one = Customer(name="Calendar Matching Customer", mobile="9100000011")
    customer_two = Customer(name="Calendar Excluded Customer", mobile="9100000012")
    db_session.add_all([customer_one, customer_two])
    db_session.flush()
    db_session.add_all([
        FollowUp(
            customer_id=customer_one.id,
            assigned_user_id=caller_one.id,
            due_at=datetime(2026, 10, 10, 10, 0),
            purpose="Calendar matching follow-up",
            completed=False,
        ),
        FollowUp(
            customer_id=customer_two.id,
            assigned_user_id=caller_two.id,
            due_at=datetime(2026, 10, 11, 10, 0),
            purpose="Calendar excluded follow-up",
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
    db_session.flush()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = calendar_dashboard(
        _calendar_request(
            b"start_date=2026-10-10&end_date=2026-10-10&caller_id=" + str(caller_one.id).encode()
        ),
        db_session,
    )

    assert isinstance(response, HTMLResponse)
    body = response.body.decode()
    assert response.status_code == 200
    assert "Calendar matching follow-up" in body
    assert "Calendar Matching Customer" in body
    assert "Calendar Excluded Customer" not in body
    assert "Calendar excluded follow-up" not in body


def test_monitoring_calendar_rejects_non_admin_roles(db_session, monkeypatch):
    import app.routers.lead_visit_monitoring as routes

    caller = _user(db_session, "calendar-unauthorized-regression", "TELECALLER")
    monkeypatch.setattr(routes, "_actor", lambda request, db: caller)

    response = calendar_dashboard(_calendar_request(), db_session)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_monitoring_calendar_reports_invalid_and_reversed_dates(db_session, monkeypatch):
    import app.routers.lead_visit_monitoring as routes

    admin = _user(db_session, "calendar-invalid-regression", "ADMIN")
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    invalid = calendar_dashboard(
        _calendar_request(b"start_date=not-a-date&caller_id=not-a-user"),
        db_session,
    )
    assert isinstance(invalid, HTMLResponse)
    assert "Start date is invalid" in invalid.body.decode()
    assert "Caller filter is invalid" in invalid.body.decode()

    reversed_range = calendar_dashboard(
        _calendar_request(b"start_date=2026-10-12&end_date=2026-10-10"),
        db_session,
    )
    assert isinstance(reversed_range, HTMLResponse)
    assert "Start date must be on or before end date" in reversed_range.body.decode()


def test_monitoring_calendar_is_registered_in_production_entrypoint():
    from app.main_portal import app as production_app

    paths = {getattr(route, "path", None) for route in production_app.routes}
    assert "/admin/lead-monitoring/calendar" in paths
