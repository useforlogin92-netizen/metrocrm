from app.auth import allowed_methods
from app.portal import app


def _route(path: str, method: str):
    matches = [
        route
        for route in app.router.routes
        if route.path == path and method in getattr(route, "methods", set())
    ]
    assert matches, f"missing route: {method} {path}"
    return matches[-1]


def test_role_verification_methods_match_login_policy():
    assert allowed_methods("SUPER_ADMIN") == ["mobile_otp", "email_otp", "security_question"]
    assert allowed_methods("ADMIN") == ["mobile_otp", "email_otp", "approval"]
    assert allowed_methods("SALES_EXECUTIVE") == ["mobile_otp", "email_otp", "approval"]


def test_single_login_routes_exist():
    assert _route("/", "GET")
    assert _route("/auth/login", "POST")
    assert _route("/auth/verify", "POST")
    assert _route("/admin/login", "GET")
    assert _route("/super-admin/login", "GET")
    assert _route("/super-admin/login-requests", "GET")


def test_common_login_route_is_owned_by_portal_module():
    """The live common login flow remains owned by the portal module."""
    for path in ("/auth/login", "/auth/verify"):
        route = _route(path, "POST")
        assert route.endpoint.__module__ == "app.portal"


def test_single_login_is_role_neutral():
    """All roles enter through the same authentication endpoint."""
    assert _route("/auth/login", "POST").endpoint.__name__ == "staff_login"
    assert _route("/auth/login", "POST").endpoint.__module__ == "app.portal"
