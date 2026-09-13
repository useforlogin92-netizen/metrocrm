import asyncio

from starlette.types import Scope

from app.logout_cookie_hardening import LogoutCookieHardeningMiddleware


def test_logout_cookie_hardening_expires_session_cookie():
    sent = []

    async def app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 303,
            "headers": [(b"location", b"/")],
        })
        await send({"type": "http.response.body", "body": b""})

    async def run():
        async def receive():
            return {"type": "http.request"}

        async def send(message):
            sent.append(message)

        scope: Scope = {
            "type": "http",
            "path": "/auth/logout",
            "method": "GET",
            "headers": [],
        }
        await LogoutCookieHardeningMiddleware(app)(scope, receive, send)

    asyncio.run(run())
    cookies = [value for key, value in sent[0]["headers"] if key == b"set-cookie"]
    assert any(b"session=" in cookie and b"Max-Age=0" in cookie for cookie in cookies)


def test_logout_cookie_hardening_does_not_touch_other_routes():
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def run():
        async def receive():
            return {"type": "http.request"}

        async def send(message):
            sent.append(message)

        scope: Scope = {
            "type": "http",
            "path": "/dashboard",
            "method": "GET",
            "headers": [],
        }
        await LogoutCookieHardeningMiddleware(app)(scope, receive, send)

    asyncio.run(run())
    assert sent[0]["headers"] == []
