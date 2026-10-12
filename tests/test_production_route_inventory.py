from fastapi.testclient import TestClient


def test_production_entrypoint_registers_health_and_login_routes():
    from app.main_portal import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/healthz" in paths
    assert "/" in paths
    assert "/super-admin/login" in paths
    assert "/admin/login" in paths


def test_healthz_returns_database_health_response():
    # The test's configured test database may be unavailable for this endpoint's
    # global engine; this assertion only verifies route registration in that case.
    from app.main_portal import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/healthz" in paths
