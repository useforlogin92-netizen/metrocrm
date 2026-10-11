from datetime import datetime

from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.models import AuditEvent, SiteVisit, User
from app.routers import site_visit_workflow as workflow
from app.site_visit_workflow_models import SiteVisitCheckIn


def _request(path="/site-visits/1/check-in"):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
        "root_path": "",
        "session": {"csrf_token": "test-csrf"},
    })


def test_gps_coordinates_are_range_and_finiteness_checked():
    assert workflow._valid_gps_coordinates(19.0760, 72.8777, 12.5)
    assert workflow._valid_gps_coordinates(0, 0)
    assert not workflow._valid_gps_coordinates(91, 0)
    assert not workflow._valid_gps_coordinates(0, 181)
    assert not workflow._valid_gps_coordinates(float("nan"), 0)
    assert not workflow._valid_gps_coordinates(0, float("inf"))
    assert not workflow._valid_gps_coordinates(0, 0, -1)
    assert not workflow._valid_gps_coordinates(0, 0, float("nan"))


def test_gps_checkin_model_is_isolated_and_unique_per_visit():
    assert SiteVisitCheckIn.__tablename__ == "site_visit_checkins"
    assert SiteVisitCheckIn.__table__.c.visit_id.unique
    assert {"latitude", "longitude", "accuracy_m", "captured_at", "actor_user_id"}.issubset(
        SiteVisitCheckIn.__table__.columns.keys()
    )


def test_assigned_caller_can_record_one_gps_checkin_and_duplicate_is_rejected(db_session, monkeypatch):
    actor = User(
        username="gps-checkin-caller",
        password_hash="x",
        role="SALES_EXECUTIVE",
        is_active=True,
        is_approved=True,
    )
    db_session.add(actor)
    db_session.flush()
    visit = SiteVisit(
        lead_id=None,
        customer_id=None,
        project_id=None,
        sales_employee_id=actor.id,
        conducted_by_id=actor.id,
        scheduled_at=datetime(2026, 10, 11, 10, 0),
        status="SCHEDULED",
    )
    db_session.add(visit)
    db_session.commit()
    monkeypatch.setattr(workflow, "_actor", lambda request, db: actor)

    response = workflow.record_visit_checkin(
        visit.id, _request(f"/site-visits/{visit.id}/check-in"),
        latitude=19.0760, longitude=72.8777, accuracy_m=12.5,
        csrf_token_value="test-csrf", db=db_session,
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    saved = db_session.query(SiteVisitCheckIn).filter_by(visit_id=visit.id).one()
    assert float(saved.latitude) == 19.076
    assert float(saved.longitude) == 72.8777
    assert float(saved.accuracy_m) == 12.5
    assert saved.actor_user_id == actor.id
    assert db_session.query(AuditEvent).filter_by(action="SITE_VISIT_GPS_CHECKIN_RECORDED").count() == 1

    duplicate = workflow.record_visit_checkin(
        visit.id, _request(f"/site-visits/{visit.id}/check-in"),
        latitude=19.0761, longitude=72.8778, accuracy_m=10,
        csrf_token_value="test-csrf", db=db_session,
    )
    assert duplicate.status_code == 409
    assert db_session.query(SiteVisitCheckIn).filter_by(visit_id=visit.id).count() == 1


def test_cancelled_visit_cannot_record_gps_checkin(db_session, monkeypatch):
    actor = User(
        username="gps-checkin-cancelled",
        password_hash="x",
        role="SALES_EXECUTIVE",
        is_active=True,
        is_approved=True,
    )
    db_session.add(actor)
    db_session.flush()
    visit = SiteVisit(
        sales_employee_id=actor.id,
        conducted_by_id=actor.id,
        scheduled_at=datetime(2026, 10, 11, 10, 0),
        status="CANCELLED",
    )
    db_session.add(visit)
    db_session.commit()
    monkeypatch.setattr(workflow, "_actor", lambda request, db: actor)

    response = workflow.record_visit_checkin(
        visit.id, _request(f"/site-visits/{visit.id}/check-in"),
        latitude=19.0760, longitude=72.8777, accuracy_m=12.5,
        csrf_token_value="test-csrf", db=db_session,
    )
    assert response.status_code == 409
    assert db_session.query(SiteVisitCheckIn).filter_by(visit_id=visit.id).count() == 0



def test_unassigned_caller_cannot_record_another_callers_gps_checkin(db_session, monkeypatch):
    actor = User(
        username="gps-checkin-unassigned",
        password_hash="x",
        role="SALES_EXECUTIVE",
        is_active=True,
        is_approved=True,
    )
    assigned_caller = User(
        username="gps-checkin-other-caller",
        password_hash="x",
        role="SALES_EXECUTIVE",
        is_active=True,
        is_approved=True,
    )
    db_session.add_all([actor, assigned_caller])
    db_session.flush()
    visit = SiteVisit(
        sales_employee_id=assigned_caller.id,
        conducted_by_id=assigned_caller.id,
        scheduled_at=datetime(2026, 10, 11, 10, 0),
        status="SCHEDULED",
    )
    db_session.add(visit)
    db_session.commit()
    monkeypatch.setattr(workflow, "_actor", lambda request, db: actor)

    response = workflow.record_visit_checkin(
        visit.id, _request(f"/site-visits/{visit.id}/check-in"),
        latitude=19.0760, longitude=72.8777, accuracy_m=12.5,
        csrf_token_value="test-csrf", db=db_session,
    )
    assert response.status_code == 404
    assert db_session.query(SiteVisitCheckIn).filter_by(visit_id=visit.id).count() == 0



def test_invalid_gps_coordinates_are_rejected_before_persistence(db_session, monkeypatch):
    actor = User(
        username="gps-checkin-invalid-coordinates",
        password_hash="x",
        role="SALES_EXECUTIVE",
        is_active=True,
        is_approved=True,
    )
    db_session.add(actor)
    db_session.flush()
    visit = SiteVisit(
        sales_employee_id=actor.id,
        conducted_by_id=actor.id,
        scheduled_at=datetime(2026, 10, 11, 10, 0),
        status="SCHEDULED",
    )
    db_session.add(visit)
    db_session.commit()
    monkeypatch.setattr(workflow, "_actor", lambda request, db: actor)

    response = workflow.record_visit_checkin(
        visit.id, _request(f"/site-visits/{visit.id}/check-in"),
        latitude=91, longitude=72.8777, accuracy_m=12.5,
        csrf_token_value="test-csrf", db=db_session,
    )
    assert response.status_code == 422
    assert db_session.query(SiteVisitCheckIn).filter_by(visit_id=visit.id).count() == 0


def test_no_show_visit_cannot_record_gps_checkin(db_session, monkeypatch):
    actor = User(
        username="gps-checkin-no-show",
        password_hash="x",
        role="SALES_EXECUTIVE",
        is_active=True,
        is_approved=True,
    )
    db_session.add(actor)
    db_session.flush()
    visit = SiteVisit(
        sales_employee_id=actor.id,
        conducted_by_id=actor.id,
        scheduled_at=datetime(2026, 10, 11, 10, 0),
        status="NO_SHOW",
    )
    db_session.add(visit)
    db_session.commit()
    monkeypatch.setattr(workflow, "_actor", lambda request, db: actor)

    response = workflow.record_visit_checkin(
        visit.id, _request(f"/site-visits/{visit.id}/check-in"),
        latitude=19.0760, longitude=72.8777, accuracy_m=12.5,
        csrf_token_value="test-csrf", db=db_session,
    )
    assert response.status_code == 409
    assert db_session.query(SiteVisitCheckIn).filter_by(visit_id=visit.id).count() == 0
