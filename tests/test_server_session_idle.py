import asyncio
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

from app import main


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
