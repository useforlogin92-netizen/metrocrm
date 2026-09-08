from datetime import datetime, timedelta
import json

from app.models import Booking, Lead, User
from app.routers.advanced_reports import _bounds, _business_report, _scope_ids


def test_business_report_supports_all_periods_and_custom_range():
    for period in ["weekly", "monthly", "quarterly", "yearly"]:
        start, end, label = _bounds(period)
        assert start <= end
        assert " to " in label
    start, end, label = _bounds("custom", "2026-01-10", "2026-03-31")
    assert start.date().isoformat() == "2026-01-10"
    assert end.date().isoformat() == "2026-03-31"
    assert "2026-01-10" in label and "2026-03-31" in label


def test_custom_period_rejects_reverse_dates():
    try:
        _bounds("custom", "2026-04-01", "2026-03-31")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_staff_scope_is_actor_plus_reporting_tree(db_session):
    manager = User(username="manager", password_hash="x", role="MANAGER", is_active=True, session_version=1)
    tl = User(username="tl", password_hash="x", role="TL", reporting_manager_id=None, is_active=True, session_version=1)
    user = User(username="user", password_hash="x", role="USER", is_active=True, session_version=1)
    db_session.add_all([manager, tl, user]); db_session.flush()
    tl.reporting_manager_id = manager.id
    user.reporting_manager_id = tl.id
    db_session.flush()
    assert _scope_ids(manager, db_session) == {manager.id, tl.id, user.id}


def test_business_report_is_date_scoped(db_session):
    inside = datetime(2026, 2, 10)
    outside = datetime(2025, 12, 10)
    db_session.add_all([
        Lead(source="WEB", status="NEW", created_at=inside),
        Lead(source="WEB", status="WON", created_at=outside),
        Booking(customer_id=1, booking_date=inside, sale_value=100000, booking_amount=50000, status="BOOKED"),
    ])
    # Customer FK is not enforced by SQLite in this test setup; only aggregate date scope is under test.
    db_session.commit()
    start = datetime(2026, 2, 1); end = datetime(2026, 2, 28, 23, 59, 59)
    report = _business_report(db_session, start, end)
    assert report["metrics"]["leads"] == 1
    assert report["metrics"]["won_leads"] == 0
    assert report["metrics"]["bookings"] == 1
    assert float(report["metrics"]["sales_value"]) == 100000.0
