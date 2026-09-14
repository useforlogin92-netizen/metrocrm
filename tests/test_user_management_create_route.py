from app.main_portal import app


def test_user_management_create_get_route_exists_for_legacy_ui():
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/admin/users/create"
        and "GET" in getattr(route, "methods", set())
    ]
    assert routes
    assert routes[0].endpoint.__name__ == "admin_users_create_page"
