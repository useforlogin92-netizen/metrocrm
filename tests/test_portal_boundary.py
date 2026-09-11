import asyncio
from types import SimpleNamespace

from fastapi.responses import HTMLResponse

from app import portal_boundary


def _request(path, session):
    return SimpleNamespace(url=SimpleNamespace(path=path), session=session)


def _run_boundary(request, call_next):
    return asyncio.run(portal_boundary.enforce_dedicated_portal_session(request, call_next))


def test_required_portal_mapping():
    assert portal_boundary._required_portal("/admin") == "admin"
    assert portal_boundary._required_portal("/admin/customers") == "admin"
    assert portal_boundary._required_portal("/admin/users") == "admin"
    assert portal_boundary._required_portal("/admin/users/123/edit") == "admin"
    assert portal_boundary._required_portal("/super-admin") == "super_admin"
    assert portal_boundary._required_portal("/super-admin/login-requests") == "super_admin"
    assert portal_boundary._required_portal("/dashboard") is None


def test_super_admin_session_is_redirected_from_admin_level_surfaces():
    for path in ("/admin", "/admin/users", "/admin/property-data", "/admin/business-reports", "/admin/data-tools"):
        request = _request(path, {"user_id": 1, "login_portal": "super_admin"})

        async def call_next(_request):
            return "next"

        response = _run_boundary(request, call_next)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_super_admin_user_management_uses_dedicated_url_bridge():
    request = SimpleNamespace(
        url=SimpleNamespace(path="/super-admin/users/123/edit"),
        session={"user_id": 1, "login_portal": "super_admin"},
        scope={"path": "/super-admin/users/123/edit", "raw_path": b"/super-admin/users/123/edit"},
    )

    assert portal_boundary._super_admin_user_management_bridge(request) is True
    assert request.scope["path"] == "/admin/users/123/edit"
    assert request.scope["raw_path"] == b"/admin/users/123/edit"


def test_super_admin_user_management_response_links_use_dedicated_url():
    response = HTMLResponse(
        '<a href="/admin/users">User Management</a>'
        '<form action="/admin/users/7/reset-password" method="post"></form>'
    )

    rewritten = portal_boundary._rewrite_super_admin_user_management_links(response)
    assert b'/super-admin/users"' in rewritten.body
    assert b"/super-admin/users/7/reset-password" in rewritten.body
    assert b"/admin/users" not in rewritten.body


def test_super_admin_session_can_reach_super_admin_surfaces():
    for path in ("/super-admin", "/super-admin/login-requests"):
        request = _request(path, {"user_id": 1, "login_portal": "super_admin"})

        async def call_next(_request):
            return "next"

        assert _run_boundary(request, call_next) == "next"


def test_admin_session_is_redirected_from_super_admin_surfaces():
    for path in ("/super-admin", "/super-admin/login-requests"):
        request = _request(path, {"user_id": 2, "login_portal": "admin"})

        async def call_next(_request):
            return "next"

        response = _run_boundary(request, call_next)
        assert response.status_code == 303
        assert response.headers["location"] == "/super-admin/login"


def test_admin_session_can_reach_admin_surfaces():
    request = _request("/admin/customers", {"user_id": 1, "login_portal": "admin"})

    async def call_next(_request):
        return "next"

    assert _run_boundary(request, call_next) == "next"


def test_portal_login_pages_do_not_auto_accept_mismatched_sessions():
    for path, session in (
        ("/admin/login", {"user_id": 1, "login_portal": "super_admin"}),
        ("/super-admin/login", {"user_id": 2, "login_portal": "admin"}),
    ):
        request = _request(path, session)

        async def call_next(_request):
            return "login-page"

        assert _run_boundary(request, call_next) == "login-page"


def test_unauthenticated_portal_request_passes_through_to_route_guard():
    request = _request("/super-admin/login", {})

    async def call_next(_request):
        return "next"

    assert _run_boundary(request, call_next) == "next"
