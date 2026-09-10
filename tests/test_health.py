from app.main_portal import app


def test_healthz_route_is_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/healthz" in paths


def test_healthz_handler_contract():
    route = next(route for route in app.routes if getattr(route, "path", None) == "/healthz")
    assert "GET" in getattr(route, "methods", set())
    assert route.endpoint() == {"status": "ok"}
