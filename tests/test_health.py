from fastapi.testclient import TestClient

from app.main_portal import app


def test_healthz_route_is_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/healthz" in paths


def test_healthz_returns_ok_with_test_database():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
