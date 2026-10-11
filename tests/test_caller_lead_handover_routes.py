from app.main import app


def test_caller_report_and_transfer_routes_are_registered():
    routes = [
        route for route in app.routes
        if getattr(route, "path", None) in {
            "/admin/lead-monitoring/report/{lead_id}",
            "/admin/lead-monitoring/transfer-lead",
        }
    ]
    route_methods = {(route.path, method) for route in routes for method in (getattr(route, "methods", None) or set())}
    assert ("/admin/lead-monitoring/report/{lead_id}", "GET") in route_methods
    assert ("/admin/lead-monitoring/transfer-lead", "POST") in route_methods
