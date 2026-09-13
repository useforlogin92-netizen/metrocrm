from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class LogoutCookieHardeningMiddleware:
    """Force-expire the browser session cookie when the logout endpoint completes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") != "http" or scope.get("path") != "/auth/logout":
            await self.app(scope, receive, send)
            return

        async def send_with_expired_cookie(message):
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (
                        b"set-cookie",
                        b"session=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax",
                    )
                )
                message = dict(message)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_expired_cookie)


def install_logout_cookie_hardening(app) -> None:
    """Install outside the application routes so logout always expires the cookie."""
    from starlette.middleware import Middleware

    if any(m.cls is LogoutCookieHardeningMiddleware for m in app.user_middleware):
        return
    app.user_middleware.insert(0, Middleware(LogoutCookieHardeningMiddleware))
