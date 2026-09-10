from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.portal import _portal_session_matches, admin_login_page


def _request(session):
    return SimpleNamespace(session=session)


def test_admin_portal_requires_admin_portal_session():
    assert _portal_session_matches(_request({"user_id": 1, "login_portal": "super_admin"}), "admin") is False
    assert _portal_session_matches(_request({"user_id": 1, "login_portal": "staff"}), "admin") is False
    assert _portal_session_matches(_request({"user_id": 1, "login_portal": "admin"}), "admin") is True


def test_super_admin_session_does_not_redirect_from_admin_login():
    response = admin_login_page(_request({"user_id": 1, "login_portal": "super_admin"}))
    assert not isinstance(response, RedirectResponse)


def test_unauthenticated_admin_login_still_renders_login():
    response = admin_login_page(_request({}))
    assert not isinstance(response, RedirectResponse)
