from app import portal_boundary
import app.property_portal_fix  # noqa: F401


def test_super_admin_property_navigation_has_dedicated_aliases():
    routes = dict(portal_boundary._SUPER_ADMIN_LEGACY_ROUTES)
    assert routes["/admin/media-catalog"] == "/super-admin/media-catalog"
    assert routes["/admin/property-data/whatsapp-import"] == "/super-admin/property-data/whatsapp-import"


def test_super_admin_legacy_redirect_targets_dedicated_property_urls():
    assert portal_boundary._super_admin_redirect_for_legacy_admin_path("/admin/media-catalog") == "/super-admin/media-catalog"
    assert portal_boundary._super_admin_redirect_for_legacy_admin_path("/admin/property-data/whatsapp-import") == "/super-admin/property-data/whatsapp-import"
