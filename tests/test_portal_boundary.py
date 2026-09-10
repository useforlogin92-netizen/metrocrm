from types import SimpleNamespace

import pytest

from app import portal_boundary


def _request(path, session):
    return SimpleNamespace(url=SimpleNamespace(path=path), session=session)


def test_required_portal_mapping():
    assert portal_boundary._required_portal("/admin") == "admin"
    assert portal_boundary._required_portal("/admin/customers") == "admin"
    assert portal_boundary._required_portal("/super-admin") == "super_admin"
    assert portal_boundary._required_portal("/super-admin/login-requests") == "super_admin"
    assert portal_boundary._required_portal("/dashboard") is None


@pytest.mark.asyncio
async def test_super_admin_session_is_redirected_from_admin_portal():
    request = _request("/admin/customers", {"user_id": 1, "login_portal": "super_admin"})
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return "next"

    response = await portal_boundary.enforce_dedicated_portal_session(request, call_next)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert called is False


@pytest.mark.asyncio
async def test_admin_session_is_redirected_from_super_admin_portal():
    request = _request("/super-admin/login-requests", {"user_id": 2, "login_portal": "admin"})

    async def call_next(_request):
        return "next"

    response = await portal_boundary.enforce_dedicated_portal_session(request, call_next)
    assert response.status_code == 303
    assert response.headers["location"] == "/super-admin/login"


@pytest.mark.asyncio
async def test_matching_portal_session_passes_through():
    request = _request("/admin/customers", {"user_id": 1, "login_portal": "admin"})

    async def call_next(_request):
        return "next"

    assert await portal_boundary.enforce_dedicated_portal_session(request, call_next) == "next"


@pytest.mark.asyncio
async def test_unauthenticated_portal_request_passes_through_to_route_guard():
    request = _request("/super-admin/login", {})

    async def call_next(_request):
        return "next"

    assert await portal_boundary.enforce_dedicated_portal_session(request, call_next) == "next"
