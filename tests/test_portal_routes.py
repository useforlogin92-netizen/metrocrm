from pathlib import Path

from app.portal import app


TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"
BACKUP_ROUTER = Path(__file__).resolve().parents[1] / "app" / "routers" / "backups.py"


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


def test_login_template_posts_super_admin_to_dedicated_endpoint():
    template = (TEMPLATES / "login.html").read_text(encoding="utf-8")
    assert 'action="{% if super_admin_only %}/auth/super-admin/login{% else %}/auth/login{% endif %}"' in template


def test_login_template_has_no_unrelated_om_krishna_group_branding():
    template = (TEMPLATES / "login.html").read_text(encoding="utf-8").lower()
    assert "om krishna group" not in template
    assert "om krishna" not in template


def test_backup_status_redirects_expired_or_invalid_sessions():
    source = BACKUP_ROUTER.read_text(encoding="utf-8")
    assert 'if not user:' in source
    assert 'request.session.clear()' in source
    assert 'RedirectResponse("/super-admin/login", status_code=303)' in source
