import json

from fastapi.responses import JSONResponse

from app.main_portal import app
from app.routers.health import healthz


def test_healthz_route_is_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/healthz" in paths


def test_healthz_returns_ok_when_database_is_available():
    class FakeDB:
        def execute(self, statement):
            return None

    assert healthz(FakeDB()) == {"status": "ok"}


def test_healthz_returns_503_when_database_is_unavailable():
    class BrokenDB:
        def execute(self, statement):
            raise RuntimeError("db down")

    response = healthz(BrokenDB())
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert json.loads(response.body) == {"status": "unhealthy"}
