from fastapi.testclient import TestClient

from app.main_portal import app


def test_healthz_route_is_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/healthz" in paths


def test_healthz_returns_ok_when_database_is_available(monkeypatch):
    class FakeResult:
        def __init__(self):
            pass

    class FakeDB:
        def execute(self, statement):
            return FakeResult()

    from app.routers import health

    client = TestClient(app)
    monkeypatch.setattr(health, "get_db", lambda: iter([FakeDB()]))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
