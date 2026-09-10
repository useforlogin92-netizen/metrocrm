from types import SimpleNamespace

from app import main_portal
from app.routers import password_reset_requests


def _request(session=None):
    return SimpleNamespace(session=session or {}, client=SimpleNamespace(host="127.0.0.1"), url=SimpleNamespace(path="/forgot-password"))


def test_recovery_routes_are_registered():
    paths = {getattr(route, "path", None) for route in main_portal.app.routes}
    assert "/forgot-password" in paths
    assert "/forgot-password/status" in paths
    assert "/forgot-password/reset" in paths
    assert "/password-reset-requests" in paths


def test_admin_approval_is_super_admin_only():
    admin = SimpleNamespace(role="ADMIN")
    staff = SimpleNamespace(role="MANAGER")
    assert password_reset_requests._config(_request(), admin, "approval", "token")["allowed_approvers"] == ["SUPER_ADMIN"]
    assert password_reset_requests._config(_request(), staff, "approval", "token")["allowed_approvers"] == ["ADMIN", "SUPER_ADMIN"]
