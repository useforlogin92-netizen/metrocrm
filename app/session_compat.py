"""Compatibility guard for authenticated sessions created before idle timestamps or portal identity existed."""
from __future__ import annotations

import time

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import User
from starlette.types import ASGIApp, Receive, Scope, Send


class SessionActivityCompatibilityMiddleware:
    """Preserve valid signed sessions created before newer session fields existed.

    SessionMiddleware must be outside this middleware so ``scope['session']`` is
    already available. Normal authentication/session-version checks still run
    in the application.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") == "http":
            session = scope.get("session")
            if session is not None and session.get("user_id"):
                if not session.get("last_activity"):
                    session["last_activity"] = time.time()

                # Sessions created before the dedicated Admin/Super Admin
                # portals existed may not contain ``login_portal``. Recover
                # the portal from the authenticated user role so a valid
                # Super Admin session is never mistaken for an Admin session
                # (and vice versa) when opening a protected navigation link.
                if not session.get("login_portal"):
                    db = SessionLocal()
                    try:
                        user = db.get(User, session.get("user_id"))
                        if user and user.is_active:
                            role = str(user.role or "").upper()
                            session["login_portal"] = (
                                "super_admin"
                                if role == "SUPER_ADMIN"
                                else "admin"
                                if role == "ADMIN"
                                else "staff"
                            )
                    except SQLAlchemyError:
                        # CI/unit-test databases may intentionally use a separate
                        # in-memory engine. A missing compatibility lookup must not
                        # invalidate an otherwise valid signed session.
                        pass
                    finally:
                        db.close()
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
