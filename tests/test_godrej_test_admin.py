from app.main_portal import app


def test_godrej_test_cleanup_route_is_registered():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/super-admin/property-data/delete-godrej-nest", ("POST",)) in routes
