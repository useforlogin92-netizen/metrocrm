from app.main import app


def test_caller_assignment_routes_are_registered():
    routes = [
        route for route in app.routes
        if getattr(route, "path", None) in {
            "/caller/leads",
            "/caller/leads/{lead_id}/assign",
        }
    ]
    route_methods = {
        (route.path, method)
        for route in routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/caller/leads", "GET") in route_methods
    assert ("/caller/leads/{lead_id}/assign", "POST") in route_methods


def test_assignment_post_requires_csrf_and_assignment_reason():
    from app.routers.caller_leads import assign_caller_lead
    import inspect

    signature = inspect.signature(assign_caller_lead)
    assert "_csrf" in signature.parameters
    assert "reason" in signature.parameters
    # Length limits are enforced by FastAPI form validation at request time.


def test_whatsapp_number_normalization_for_indian_and_international_numbers():
    from app.routers.caller_leads import _whatsapp_digits

    assert _whatsapp_digits("98765 43210") == "919876543210"
    assert _whatsapp_digits("0 98765 43210") == "919876543210"
    assert _whatsapp_digits("0091-9876543210") == "919876543210"
    assert _whatsapp_digits("+1 (415) 555-2671") == "14155552671"
    assert _whatsapp_digits("12345") == ""


def test_assignment_role_scope_helpers_keep_callers_team_limited():
    from app.routers.caller_leads import _visible_user_ids

    class FakeScalars:
        def all(self):
            return []

    class FakeDB:
        def scalars(self, _query):
            return FakeScalars()

    class FakeUser:
        id = 42
        role = "TL"

    assert _visible_user_ids(FakeUser(), FakeDB()) == {42}
