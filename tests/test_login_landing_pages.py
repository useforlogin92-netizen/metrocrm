from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app import main


def test_login_destination_is_role_aware_and_preserves_admin_boundary():
    assert main._login_destination("SUPER_ADMIN") == "/super-admin/property-data"
    assert main._login_destination("ADMIN") == "/admin/property-data"
    assert main._login_destination("SALES_EXECUTIVE") == "/dashboard"
    assert main._login_destination("TELECALLER") == "/dashboard"
    assert main._login_destination("MANAGER") == "/dashboard"


def test_root_redirects_authenticated_users_to_their_role_landing_page():
    cases = (
        ("SUPER_ADMIN", "/super-admin/property-data"),
        ("ADMIN", "/admin/property-data"),
        ("SALES_EXECUTIVE", "/dashboard"),
        ("TELECALLER", "/dashboard"),
    )

    for role, expected in cases:
        user = SimpleNamespace(
            id=7,
            role=role,
            is_active=True,
            session_version=3,
        )

        class FakeDB:
            def get(self, model, user_id):
                assert user_id == 7
                return user

        request = SimpleNamespace(
            session={"user_id": 7, "session_version": 3},
        )
        response = main.root(request, FakeDB())

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 303
        assert response.headers["location"] == expected


def test_login_template_has_guarded_clock_and_staff_specific_footer():
    from pathlib import Path

    template = Path("app/templates/login.html").read_text(encoding="utf-8")

    assert "function updateLiveClock()" in template
    assert "DOMContentLoaded" in template
    assert '{% if super_admin_only %}<div class="super-note">' in template
    assert "Authorized staff &amp; sales executive access only" in template
