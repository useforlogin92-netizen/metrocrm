import asyncio
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import Scope

from app.main_portal import app
from app.session_compat import SessionActivityCompatibilityMiddleware, install_session_compatibility


def test_production_entrypoint_installs_session_compatibility_inside_session_middleware():
    classes = [middleware.cls for middleware in app.user_middleware]
    assert SessionMiddleware in classes
    assert SessionActivityCompatibilityMiddleware in classes
    assert classes.index(SessionActivityCompatibilityMiddleware) > classes.index(SessionMiddleware)


def test_legacy_authenticated_session_gets_idle_timestamp():
    captured = {}

    async def endpoint(scope, receive, send):
        captured.update(scope["session"])

    middleware = SessionActivityCompatibilityMiddleware(endpoint)
    scope = {"type": "http", "session": {"user_id": 42, "login_portal": "super_admin"}}
    asyncio.run(middleware(scope, None, None))
    assert captured["user_id"] == 42
    assert isinstance(captured["last_activity"], float)


def test_existing_activity_is_not_reset_by_compatibility_middleware():
    captured = {}
    existing = 1234567890.0

    async def endpoint(scope, receive, send):
        captured.update(scope["session"])

    middleware = SessionActivityCompatibilityMiddleware(endpoint)
    scope = {"type": "http", "session": {"user_id": 42, "last_activity": existing}}
    asyncio.run(middleware(scope, None, None))
    assert captured["last_activity"] == existing
