from pathlib import Path

from app.portal import app


TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"
BACKUP_ROUTER = Path(__file__).resolve().parents[1] / "app" / "routers" / "backups.py"


def _post_routes(path: str):
    return [route for route in app.routes if getattr(route, "path", None) == path and "POST" in getattr(route, "methods", set())]


def test_dedicated_login_portals_exist():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/super-admin/login" in paths
    assert "/admin/login" in paths
    assert "/" in paths
    assert _post_routes("/auth/admin/login")
    assert _post_routes("/auth/super-admin/login")


def test_staff_login_guard_is_before_legacy_login_route():
    routes = _post_routes("/auth/login")
    assert routes
    assert routes[0].endpoint.__name__ == "staff_login"


def test_login_template_posts_super_admin_to_dedicated_endpoint():
    template = (TEMPLATES / "login.html").read_text(encoding="utf-8")
    assert 'action="{% if super_admin_only %}/auth/super-admin/login{% else %}/auth/login{% endif %}"' in template


def test_login_template_has_no_unrelated_om_krishna_group_branding():
    template = (TEMPLATES / "login.html").read_text(encoding="utf-8").lower()
    assert "om krishna group" not in template
    assert "om krishna" not in template


def test_backup_status_redirects_expired_or_invalid_sessions():
    source = BACKUP_ROUTER.read_text(encoding="utf-8")
    assert 'if not user:' in source
    assert 'request.session.clear()' in source
    assert 'RedirectResponse("/super-admin/login", status_code=303)' in source

def _calendar_request(query=b""):
    from starlette.requests import Request
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


def _calendar_user(db, username, role):
    from app.models import User
    user = User(username=username, password_hash="test-hash", role=role, is_active=True, is_approved=True)
    db.add(user)
    db.flush()
    return user


def test_lead_monitoring_calendar_is_registered_in_production_app():
    from app.main_portal import app as production_app
    paths = {getattr(route, "path", None) for route in production_app.routes}
    assert "/admin/lead-monitoring/calendar" in paths


def test_calendar_filters_followups_and_visits_by_date_and_caller(db_session, monkeypatch):
    from datetime import datetime
    from fastapi.responses import HTMLResponse
    import app.routers.lead_visit_monitoring as routes
    from app.models import Customer, FollowUp, SiteVisit

    admin = _calendar_user(db_session, "admin-calendar-regression", "ADMIN")
    caller_one = _calendar_user(db_session, "caller-calendar-regression-one", "TELECALLER")
    caller_two = _calendar_user(db_session, "caller-calendar-regression-two", "SALES_EXECUTIVE")
    customer_one = Customer(name="Calendar Matching Customer", mobile="9100000011")
    customer_two = Customer(name="Calendar Excluded Customer", mobile="9100000012")
    db_session.add_all([customer_one, customer_two])
    db_session.flush()
    db_session.add_all([
        FollowUp(customer_id=customer_one.id, assigned_user_id=caller_one.id,
                 due_at=datetime(2026, 10, 10, 10, 0), purpose="Calendar matching follow-up", completed=False),
        FollowUp(customer_id=customer_two.id, assigned_user_id=caller_two.id,
                 due_at=datetime(2026, 10, 11, 10, 0), purpose="Calendar excluded follow-up", completed=False),
        SiteVisit(customer_id=customer_one.id, sales_employee_id=caller_one.id,
                  scheduled_at=datetime(2026, 10, 10, 14, 0), status="SCHEDULED"),
        SiteVisit(customer_id=customer_two.id, sales_employee_id=caller_two.id,
                  scheduled_at=datetime(2026, 10, 11, 14, 0), status="SCHEDULED"),
    ])
    db_session.commit()
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)

    response = routes.calendar_dashboard(
        _calendar_request(b"start_date=2026-10-10&end_date=2026-10-10&caller_id=" + str(caller_one.id).encode()),
        db_session,
    )
    assert isinstance(response, HTMLResponse)
    body = response.body.decode()
    assert response.status_code == 200
    assert "Calendar matching follow-up" in body
    assert "Calendar Matching Customer" in body
    assert "Calendar Excluded Customer" not in body
    assert "Calendar excluded follow-up" not in body


def test_calendar_rejects_non_admin_roles(db_session, monkeypatch):
    from fastapi.responses import RedirectResponse
    import app.routers.lead_visit_monitoring as routes

    caller = _calendar_user(db_session, "calendar-regression-unauthorized", "TELECALLER")
    monkeypatch.setattr(routes, "_actor", lambda request, db: caller)
    response = routes.calendar_dashboard(_calendar_request(), db_session)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_calendar_invalid_filters_show_warning_without_crashing(db_session, monkeypatch):
    from fastapi.responses import HTMLResponse
    import app.routers.lead_visit_monitoring as routes

    admin = _calendar_user(db_session, "admin-calendar-invalid-regression", "ADMIN")
    monkeypatch.setattr(routes, "_actor", lambda request, db: admin)
    response = routes.calendar_dashboard(_calendar_request(b"start_date=not-a-date&caller_id=not-a-user"), db_session)
    assert isinstance(response, HTMLResponse)
    body = response.body.decode()
    assert response.status_code == 200
    assert "Start date is invalid" in body
    assert "Caller filter is invalid" in body

