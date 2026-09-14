from app.main_portal import app


def test_godrej_test_cleanup_route_is_registered():
    routes = {
        (route.path, tuple(sorted(getattr(route, "methods", set()) or set())))
        for route in app.routes
        if hasattr(route, "methods")
    }
    assert ("/super-admin/property-data/delete-godrej-nest", ("POST",)) in routes
