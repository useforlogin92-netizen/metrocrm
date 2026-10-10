"""Production entrypoint route-registration regression tests."""

from app.main_portal import app as production_app


def test_production_entrypoint_registers_caller_leads_route():
    matching_routes = [
        route
        for route in production_app.routes
        if getattr(route, "path", None) == "/caller/leads"
    ]

    assert matching_routes, (
        "The production ASGI entrypoint must register GET /caller/leads; "
        "Render serves app.main_portal:app."
    )
    assert any("GET" in getattr(route, "methods", set()) for route in matching_routes)


def test_render_health_check_route_is_registered():
    matching_routes = [
        route
        for route in production_app.routes
        if getattr(route, "path", None) == "/healthz"
    ]

    assert matching_routes, "render.yaml healthCheckPath must resolve to /healthz"
    assert any("GET" in getattr(route, "methods", set()) for route in matching_routes)
