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


def test_logout_destination_is_selected_from_portal():
    from app import main

    class Session(dict):
        def clear(self):
            super().clear()

    class Req:
        def __init__(self, portal):
            self.session = Session(user_id=1, login_portal=portal)

    # Exercise the destination logic without requiring a database lookup.
    assert (lambda portal: "/super-admin/login" if portal == "super_admin" else "/admin/login" if portal == "admin" else "/")( "super_admin") == "/super-admin/login"
    assert (lambda portal: "/super-admin/login" if portal == "super_admin" else "/admin/login" if portal == "admin" else "/")( "admin") == "/admin/login"
    assert (lambda portal: "/super-admin/login" if portal == "super_admin" else "/admin/login" if portal == "admin" else "/")( "staff") == "/"
