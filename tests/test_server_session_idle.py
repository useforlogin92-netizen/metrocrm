import asyncio
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from app import main
from app.models import User
from app.routers.backups import require_super_admin
from app.routers.caller_search import _user as caller_user
from app.routers.catalog_sharing import _current_user as catalog_user
from app.routers.integrations import _user as integration_user


ROOT = Path(__file__).resolve().parents[1]


def _request(session: dict) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/dashboard",
        "raw_path": b"/dashboard",
        "query_string": b"",
        "headers": [(b"accept", b"text/html")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "session": session,
    }
    return Request(scope)


def test_server_idle_middleware_rejects_stale_session(monkeypatch):
    now = 2_000_000.0
    session = {"user_id": 7, "session_version": 1, "last_activity": now - main.settings.session_max_age}
    request = _request(session)
    monkeypatch.setattr(main.time, "time", lambda: now)

    async def call_next(_request):
        raise AssertionError("stale authenticated request must not reach the endpoint")

    response = asyncio.run(main.enforce_idle_session(request, call_next))

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert session == {}
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0, private"


def test_server_idle_middleware_refreshes_active_session(monkeypatch):
    now = 3_000_000.0
    session = {"user_id": 7, "session_version": 1, "last_activity": now - 30}
    request = _request(session)
    monkeypatch.setattr(main.time, "time", lambda: now)

    async def call_next(_request):
        return Response("ok")

    response = asyncio.run(main.enforce_idle_session(request, call_next))

    assert response.status_code == 200
    assert session["last_activity"] == now
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0, private"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"


def test_session_middleware_wraps_idle_enforcement_in_correct_order():
    names = [middleware.cls.__name__ for middleware in main.app.user_middleware]
    assert names[0] == "SessionMiddleware"
    assert "BaseHTTPMiddleware" in names


def test_successful_login_initializes_last_activity():
    portal = (ROOT / "app" / "portal.py").read_text(encoding="utf-8")
    assert 'request.session["last_activity"] = datetime.now(timezone.utc).timestamp()' in portal


def test_revoked_session_is_rejected_by_shared_user_guards(db_session: Session):
    user = User(username="revoked", password_hash="hash", role="SUPER_ADMIN", is_active=True, session_version=2)
    db_session.add(user)
    db_session.commit()
    stale_request = _request({"user_id": user.id, "session_version": 1, "last_activity": 3_000_000.0})

    assert main._current_user(stale_request, db_session) is None
    assert caller_user(stale_request, db_session) is None
    assert catalog_user(stale_request, db_session) is None
    try:
        integration_user(stale_request, db_session)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("integration guard accepted a revoked session")
    try:
        require_super_admin(stale_request, db_session)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("backup guard accepted a revoked session")
