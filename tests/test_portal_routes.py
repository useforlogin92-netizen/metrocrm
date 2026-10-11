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


# White-label branding validation tests
from io import BytesIO
import pytest
from PIL import Image
from app.routers.branding_settings import _validated_logo, router as branding_router


def _branding_test_png() -> bytes:
    stream = BytesIO()
    Image.new("RGBA", (64, 32), (20, 40, 60, 255)).save(stream, format="PNG")
    return stream.getvalue()


def test_branding_logo_validation_normalizes_png():
    normalized = _validated_logo(_branding_test_png())
    with Image.open(BytesIO(normalized)) as image:
        assert image.format == "PNG"
        assert image.size == (64, 32)


def test_branding_logo_validation_rejects_empty_oversized_and_invalid_images():
    with pytest.raises(ValueError, match="non-empty image"):
        _validated_logo(b"")
    with pytest.raises(ValueError, match="2 MB"):
        _validated_logo(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="valid supported image"):
        _validated_logo(b"not an image")


def test_branding_routes_register_in_production_app():
    assert {route.path for route in branding_router.routes} == {"/admin/branding", "/admin/branding/logo"}
    from app.main_portal import app as production_app
    paths = {getattr(route, "path", None) for route in production_app.routes}
    assert "/admin/branding" in paths
    assert "/admin/branding/logo" in paths


from app.routers.branding_settings import render_message_template


def test_branding_template_renderer_replaces_known_placeholders_and_preserves_unknown():
    rendered = render_message_template("Hi {{Customer_Name}} from {{Company_Name}} at {{Unknown_Field}}", {"Customer_Name": "Asha", "Company_Name": "Metro Homes"})
    assert rendered == "Hi Asha from Metro Homes at {{Unknown_Field}}"
