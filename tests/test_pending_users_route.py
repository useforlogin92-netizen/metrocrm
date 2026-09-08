from pathlib import Path

from app import main


def test_pending_users_route_and_template_are_present():
    routes = [route for route in main.app.routes if getattr(route, "path", None) == "/admin/users/pending"]
    assert any("GET" in getattr(route, "methods", set()) for route in routes)
    template = Path("app/templates/pending_users.html")
    assert template.is_file()
    assert "Approve User" in template.read_text(encoding="utf-8")
