from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.main import super_admin_login_page
from app import portal
from app.portal import _portal_session_matches, admin_login_page


def _request(session):
    return SimpleNamespace(session=session)


def test_legacy_portal_session_matcher_remains_strict():
    assert _portal_session_matches(_request({"user_id": 1, "login_portal": "super_admin"}), "admin") is False
    assert _portal_session_matches(_request({"user_id": 1, "login_portal": "staff"}), "admin") is False
    assert _portal_session_matches(_request({"user_id": 1, "login_portal": "admin"}), "admin") is True


def test_legacy_admin_login_redirects_authenticated_users_to_dashboard():
    response = admin_login_page(_request({"user_id": 1, "login_portal": "super_admin"}))
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/dashboard"


def test_legacy_super_admin_login_redirects_authenticated_users_to_dashboard():
    response = super_admin_login_page(_request({"user_id": 1, "login_portal": "admin"}))
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/dashboard"


def test_unauthenticated_legacy_login_urls_redirect_to_common_login():
    assert admin_login_page(_request({})).headers["location"] == "/"
    assert super_admin_login_page(_request({})).headers["location"] == "/"
