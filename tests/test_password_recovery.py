import asyncio
from types import SimpleNamespace

from fastapi.responses import HTMLResponse, RedirectResponse

from app import main_portal
from app.routers import password_recovery
from app.security import hash_password, verify_password


def _request(session=None):
    return SimpleNamespace(
        session=session if session is not None else {},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(path="/super-admin/login"),
    )


def test_super_admin_recovery_routes_are_registered():
    paths = {getattr(route, "path", None) for route in main_portal.app.routes}
    assert "/super-admin/forgot-password" in paths
    assert "/super-admin/forgot-password/reset" in paths


def test_super_admin_login_get_receives_forgot_password_link():
    request = _request()

    async def call_next(_request):
        return HTMLResponse("<form></form>")

    response = asyncio.run(password_recovery.add_recovery_link_to_super_admin_login(request, call_next))
    assert b"/super-admin/forgot-password" in response.body
    assert b"Forgot your password?" in response.body


def test_recovery_reset_requires_verified_super_admin_session():
    request = _request({})

    class FakeDB:
        def get(self, _model, _user_id):
            return None

    response = password_recovery.reset_password_page(request, FakeDB())
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/super-admin/forgot-password"


def test_recovery_reset_changes_password_and_invalidates_sessions():
    old_hash = hash_password("OldPassword123")
    user = SimpleNamespace(id=7, role="SUPER_ADMIN", is_active=True, password_hash=old_hash, session_version=4)
    request = _request({
        password_recovery.RECOVERY_SESSION_USER: 7,
        password_recovery.RECOVERY_SESSION_EXPIRES: 9999999999,
    })

    class FakeDB:
        def get(self, _model, user_id):
            return user if user_id == 7 else None

        def add(self, _event):
            return None

        def commit(self):
            return None

    response = password_recovery.reset_password(request, "NewStrongPassword123", "NewStrongPassword123", FakeDB())
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/super-admin/login?password_reset=success"
    assert verify_password("NewStrongPassword123", user.password_hash)
    assert user.session_version == 5
    assert request.session == {}


def test_recovery_reset_rejects_mismatched_passwords():
    user = SimpleNamespace(id=7, role="SUPER_ADMIN", is_active=True, password_hash=hash_password("OldPassword123"), session_version=4)
    request = _request({
        password_recovery.RECOVERY_SESSION_USER: 7,
        password_recovery.RECOVERY_SESSION_EXPIRES: 9999999999,
    })

    class FakeDB:
        def get(self, _model, user_id):
            return user if user_id == 7 else None

    response = password_recovery.reset_password(request, "NewPassword123", "DifferentPassword123", FakeDB())
    assert response.status_code == 200
    assert verify_password("OldPassword123", user.password_hash)
    assert user.session_version == 4


def test_recovery_security_answer_verification_is_rate_limited(monkeypatch):
    user = SimpleNamespace(id=7, role="SUPER_ADMIN", is_active=True, security_answer_hash=hash_password("Correct Answer"))
    request = _request()

    class FakeDB:
        def scalar(self, _statement):
            return user

    monkeypatch.setattr(password_recovery, "select", lambda *_args, **_kwargs: SimpleNamespace(where=lambda *_a, **_k: object()))
    for _ in range(password_recovery._MAX_FAILURES):
        response = password_recovery.verify_recovery(request, "Satya", "wrong", FakeDB())
        assert response.status_code == 200
    locked = password_recovery.verify_recovery(request, "Satya", "wrong", FakeDB())
    assert b"temporarily locked" in locked.body
