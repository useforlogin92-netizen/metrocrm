from app.auth import allowed_methods
from app.portal import app


def test_role_verification_methods_match_login_policy():
    assert allowed_methods("SUPER_ADMIN") == ["mobile_otp", "email_otp", "security_question"]
    assert allowed_methods("ADMIN") == ["mobile_otp", "email_otp", "approval"]
    assert allowed_methods("SALES_EXECUTIVE") == ["mobile_otp", "email_otp", "approval"]


def test_dedicated_login_routes_exist():
    routes = {(route.path, method) for route in app.router.routes for method in getattr(route, "methods", set())}
    assert ("/admin/login", "GET") in routes
    assert ("/auth/admin/login", "POST") in routes
    assert ("/super-admin/login", "GET") in routes
    assert ("/auth/login", "POST") in routes
    assert ("/super-admin/login-requests", "GET") in routes
