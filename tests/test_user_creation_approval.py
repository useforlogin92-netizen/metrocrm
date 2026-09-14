from starlette.requests import Request

from app.main import create_user
from app.models import User


def _request(user_id: int = 1) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/admin/users/create",
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
        "session": {"user_id": user_id, "session_version": 1},
    })


def test_super_admin_created_user_is_auto_approved(db_session):
    db_session.add(User(
        id=1,
        username="superadmin",
        password_hash="hash",
        role="SUPER_ADMIN",
        is_active=True,
        is_approved=True,
        session_version=1,
    ))
    db_session.commit()

    response = create_user(
        _request(),
        username="new-manager",
        password="strongpass123",
        role="MANAGER",
        security_question="What is your favorite city?",
        security_answer="Mumbai",
        db=db_session,
    )

    assert response.status_code == 303
    created = db_session.query(User).filter_by(username="new-manager").one()
    assert created.is_active is True
    assert created.is_approved is True


def test_admin_created_user_still_requires_approval(db_session):
    db_session.add(User(
        id=1,
        username="admin",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
        is_approved=True,
        session_version=1,
    ))
    db_session.commit()

    response = create_user(
        _request(),
        username="new-manager",
        password="strongpass123",
        role="MANAGER",
        security_question="What is your favorite city?",
        security_answer="Mumbai",
        db=db_session,
    )

    assert response.status_code == 303
    created = db_session.query(User).filter_by(username="new-manager").one()
    assert created.is_active is True
    assert created.is_approved is False
