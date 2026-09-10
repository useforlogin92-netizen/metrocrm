"""Compatibility guard for authenticated sessions created before idle timestamps existed."""
from __future__ import annotations

import time

from starlette.types import ASGIApp, Receive, Scope, Send


class SessionActivityCompatibilityMiddleware:
    """Preserve valid signed sessions that predate the ``last_activity`` field.

    SessionMiddleware must be outside this middleware so ``scope['session']`` is
    already available. A signed session with a valid user id is trusted here;
    normal authentication/session-version checks still run in the application.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") == "http":
            session = scope.get("session")
            if session is not None and session.get("user_id") and not session.get("last_activity"):
                session["last_activity"] = time.time()
        await self.app(scope, receive, send)


def install_session_compatibility(app) -> None:
    """Insert the compatibility middleware inside SessionMiddleware.

    This is called once by the production entrypoint after the portal boundary
    has established SessionMiddleware as the outermost user middleware.
    """
    from starlette.middleware import Middleware
    from starlette.middleware.sessions import SessionMiddleware

    if any(m.cls is SessionActivityCompatibilityMiddleware for m in app.user_middleware):
        return
    session_index = next((i for i, m in enumerate(app.user_middleware) if m.cls is SessionMiddleware), None)
    if session_index is None:
        return
    app.user_middleware.insert(session_index + 1, Middleware(SessionActivityCompatibilityMiddleware))
