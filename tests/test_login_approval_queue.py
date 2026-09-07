from datetime import datetime, timedelta
import json

from starlette.requests import Request

from app.models import AuditEvent, User
from app.portal import super_admin_login_requests


def _request_for_session(user_id: int) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/super-admin/login-requests", "headers": [], "query_string": b"", "session": {"user_id": user_id}}
    return Request(scope)


def test_super_admin_queue_shows_latest_pending_admin_request(db_session):
    super_admin = User(username="sa", password_hash="x", role="SUPER_ADMIN", is_active=True, is_approved=True)
    admin = User(username="Satyapal_Admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add_all([super_admin, admin])
    db_session.flush()
    event = AuditEvent(actor_user_id=admin.id, action="LOGIN_APPROVAL_REQUEST", entity_type="User", entity_id=str(admin.id), details=json.dumps({"portal": "admin", "role": "ADMIN"}))
    db_session.add(event)
    db_session.commit()

    response = super_admin_login_requests(_request_for_session(super_admin.id), db_session)
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "Satyapal_Admin" in body
    assert f"/super-admin/login-requests/{event.id}/approve" in body


def test_super_admin_queue_hides_decided_request(db_session):
    super_admin = User(username="sa", password_hash="x", role="SUPER_ADMIN", is_active=True, is_approved=True)
    admin = User(username="admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add_all([super_admin, admin])
    db_session.flush()
    request_event = AuditEvent(actor_user_id=admin.id, action="LOGIN_APPROVAL_REQUEST", entity_type="User", entity_id=str(admin.id), details=json.dumps({"portal": "admin", "role": "ADMIN"}))
    db_session.add(request_event)
    db_session.flush()
    db_session.add(AuditEvent(actor_user_id=super_admin.id, action="LOGIN_APPROVAL_GRANTED", entity_type="User", entity_id=str(admin.id), details=json.dumps({"request_id": request_event.id, "portal": "admin", "reason": "approved_by_super_admin"})))
    db_session.commit()

    response = super_admin_login_requests(_request_for_session(super_admin.id), db_session)
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "No pending login approval requests." in body


def test_super_admin_queue_hides_expired_request(db_session):
    super_admin = User(username="sa", password_hash="x", role="SUPER_ADMIN", is_active=True, is_approved=True)
    admin = User(username="admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add_all([super_admin, admin])
    db_session.flush()
    event = AuditEvent(actor_user_id=admin.id, action="LOGIN_APPROVAL_REQUEST", entity_type="User", entity_id=str(admin.id), details=json.dumps({"portal": "admin", "role": "ADMIN"}), created_at=datetime.utcnow() - timedelta(minutes=16))
    db_session.add(event)
    db_session.commit()

    response = super_admin_login_requests(_request_for_session(super_admin.id), db_session)
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "No pending login approval requests." in body
