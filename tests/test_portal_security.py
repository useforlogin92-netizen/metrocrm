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


def test_dedicated_login_routes_exist():
    assert _route("/admin/login", "GET")
    assert _route("/auth/admin/login", "POST")
    assert _route("/super-admin/login", "GET")
    assert _route("/auth/super-admin/login", "POST")
    assert _route("/auth/login", "POST")
    assert _route("/auth/verify", "POST")
    assert _route("/super-admin/login-requests", "GET")


def test_portal_auth_routes_are_owned_by_portal_module():
    """The live portal must not expose legacy app.main auth handlers."""
    for path in ("/auth/admin/login", "/auth/super-admin/login", "/auth/login", "/auth/verify"):
        route = _route(path, "POST")
        assert route.endpoint.__module__ == "app.portal"


def test_portal_route_policy_is_separated():
    """Dedicated role portals and the common staff endpoint must remain distinct."""
    assert _route("/auth/admin/login", "POST").endpoint.__name__ == "admin_login"
    assert _route("/auth/super-admin/login", "POST").endpoint.__name__ == "super_admin_login"
    assert _route("/auth/login", "POST").endpoint.__name__ == "staff_login"
