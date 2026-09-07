from app.portal import app


def _post_routes(path: str):
    return [route for route in app.routes if getattr(route, "path", None) == path and "POST" in getattr(route, "methods", set())]


def test_dedicated_login_portals_exist():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/super-admin/login" in paths
    assert "/admin/login" in paths
    assert "/" in paths
    assert _post_routes("/auth/admin/login")
    assert _post_routes("/auth/super-admin/login")


def test_staff_login_guard_is_before_legacy_login_route():
    routes = _post_routes("/auth/login")
    assert routes
    assert routes[0].endpoint.__name__ == "staff_login"
