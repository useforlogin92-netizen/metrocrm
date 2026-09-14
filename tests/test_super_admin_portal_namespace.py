from fastapi import Request
from fastapi.responses import HTMLResponse

from app import main_portal
from app import portal_boundary


def _request(path: str, method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "scheme": "https",
        "server": ("testserver", 443),
        "client": ("127.0.0.1", 12345),
        "root_path": "",
    }
    scope["session"] = {"login_portal": "super_admin"}
    return Request(scope)


def test_main_loads_dedicated_portal_boundary():
    assert any(
        getattr(middleware, "kwargs", {}).get("dispatch").__name__ == "enforce_dedicated_portal_session"
        for middleware in main_portal.app.user_middleware
        if getattr(middleware, "kwargs", {}).get("dispatch") is not None
    )


def test_super_admin_user_actions_stay_on_dedicated_namespace():
    request = _request("/super-admin/users/3/approve", "POST")
    assert portal_boundary._super_admin_legacy_route_bridge(request) is True
    assert request.scope["path"] == "/admin/users/3/approve"

    response = portal_boundary._rewrite_super_admin_user_management_links(
        HTMLResponse('<form method="post" action="/admin/users/3/approve"></form>')
    )
    assert "/super-admin/users/3/approve" in response.body.decode("utf-8")
    assert "/admin/users/3/approve" not in response.body.decode("utf-8")


def test_dedicated_super_admin_namespace_covers_admin_scoped_pages():
    mappings = dict(portal_boundary._SUPER_ADMIN_LEGACY_ROUTES)
    expected = {
        "/admin/users": "/super-admin/users",
        "/admin/users/pending": "/super-admin/users/pending",
        "/admin/property-data": "/super-admin/property-data",
        "/admin/property-data/social": "/super-admin/property-data/social",
        "/admin/property-submissions": "/super-admin/property-submissions",
        "/admin/leads/offline-import": "/super-admin/leads/offline-import",
        "/admin/data-tools": "/super-admin/data-tools",
        "/admin/backups": "/super-admin/backups",
        "/admin/business-reports": "/super-admin/business-reports",
    }
    for legacy, dedicated in expected.items():
        assert mappings.get(legacy) == dedicated
