from app.main_portal import app
from app import portal_boundary


def test_production_entrypoint_loads_super_admin_namespace_boundary():
    assert any(
        getattr(middleware, "kwargs", {}).get("dispatch").__name__ == "enforce_dedicated_portal_session"
        for middleware in app.user_middleware
        if getattr(middleware, "kwargs", {}).get("dispatch") is not None
    )
    mappings = dict(portal_boundary._SUPER_ADMIN_LEGACY_ROUTES)
    assert mappings["/admin/users"] == "/super-admin/users"
    assert mappings["/admin/users/pending"] == "/super-admin/users/pending"
    assert mappings["/admin/property-submissions"] == "/super-admin/property-submissions"
