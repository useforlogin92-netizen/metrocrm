import json

from app.routers.catalog_sharing import _require_sharing_user
from app.models import User
from starlette.requests import Request


def request_with_user(user_id=None, session_version=1):
    scope = {"type": "http", "method": "POST", "path": "/catalog/preview", "headers": [], "session": {}}
    request = Request(scope)
    if user_id is not None:
        request.session["user_id"] = user_id
        request.session["session_version"] = session_version
    return request


def test_sharing_helper_rejects_missing_session(db_session):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _require_sharing_user(request_with_user(), db_session)
    assert exc.value.status_code == 401


def test_sharing_helper_rejects_denied_user(db_session):
    import pytest
    from fastapi import HTTPException
    user = User(username="denied", password_hash="hash", role="SALES_EXECUTIVE", permissions_json=json.dumps({"deny": {"properties": ["VIEW"]}}), is_active=True)
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _require_sharing_user(request_with_user(user.id, user.session_version), db_session)
    assert exc.value.status_code == 403
