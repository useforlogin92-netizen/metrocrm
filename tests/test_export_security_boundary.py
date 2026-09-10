import asyncio
from types import SimpleNamespace

from app import portal_boundary


def _request(path, session, method="GET", query_params=None):
    return SimpleNamespace(url=SimpleNamespace(path=path), session=session, method=method, query_params=query_params or {})


def _run_boundary(request, call_next):
    return asyncio.run(portal_boundary.enforce_dedicated_portal_session(request, call_next))


def test_admin_export_get_is_blocked_and_returns_csrf_post_form():
    request = _request("/admin/data-tools/export/Customers", {"user_id": 1, "login_portal": "admin"}, query_params={"request_id": "42"})

    async def call_next(_request):
        raise AssertionError("legacy GET export handler must not execute")

    response = _run_boundary(request, call_next)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    body = response.body.decode()
    assert "method='post'" in body
    assert "name='csrf_token'" in body
    assert "request_id=42" in body


def test_super_admin_export_get_is_blocked_and_returns_csrf_post_form():
    request = _request("/super-admin/data-export-requests/42/download", {"user_id": 1, "login_portal": "super_admin"})

    async def call_next(_request):
        raise AssertionError("legacy GET export handler must not execute")

    response = _run_boundary(request, call_next)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    body = response.body.decode()
    assert "method='post'" in body
    assert "name='csrf_token'" in body


def test_property_direct_export_get_is_blocked_and_returns_csrf_post_form():
    request = _request("/admin/property-data/export", {"user_id": 1, "login_portal": "admin"})

    async def call_next(_request):
        raise AssertionError("legacy property export GET handler must not execute")

    response = _run_boundary(request, call_next)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    body = response.body.decode()
    assert "method='post'" in body
    assert "action='/admin/property-data/export'" in body
    assert "name='csrf_token'" in body


def test_property_approved_download_get_is_blocked_and_returns_csrf_post_form():
    request = _request("/admin/property-data/export/download/42", {"user_id": 1, "login_portal": "admin"})

    async def call_next(_request):
        raise AssertionError("legacy approved property export GET handler must not execute")

    response = _run_boundary(request, call_next)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    body = response.body.decode()
    assert "method='post'" in body
    assert "action='/admin/property-data/export/download/42'" in body
    assert "name='csrf_token'" in body
