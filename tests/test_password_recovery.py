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
    assert "/super-admin/forgot-password/verify" in paths
    assert "/super-admin/forgot-password/reset" in paths
    assert "/super-admin/security-questions" in paths


def test_super_admin_login_get_receives_forgot_password_link():
    request = _request()

    async def call_next(_request):
        return HTMLResponse("<form></form>")

    response = asyncio.run(password_recovery.add_recovery_link_to_super_admin_login(request, call_next))
    assert b"/super-admin/forgot-password" in response.body
    assert b"Forgot your password?" in response.body


def test_recovery_requires_exactly_five_configured_questions():
    user = SimpleNamespace(id=7, username="Satya", role="SUPER_ADMIN", is_active=True)
    request = _request()

    class FakeDB:
        def scalar(self, _statement):
            return user

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(id=i) for i in range(1, 4)])

    response = password_recovery.start_recovery(request, "Satya", FakeDB())
    assert response.status_code == 200
    assert b"not fully configured" in response.body


def test_start_recovery_randomly_selects_two_questions():
    user = SimpleNamespace(id=7, username="Satya", role="SUPER_ADMIN", is_active=True)
    request = _request()
    questions = [SimpleNamespace(id=i, question=f"Question {i}", answer_hash=hash_password(f"answer{i}"), is_active=True) for i in range(1, 6)]

    class FakeDB:
        def scalar(self, _statement):
            return user

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: questions)

    response = password_recovery.start_recovery(request, "Satya", FakeDB())
    assert response.status_code == 200
    assert len(request.session[password_recovery.RECOVERY_SESSION_QUESTIONS]) == 2
    assert b"Security Verification" in response.body
    assert b"Question" in response.body


def test_two_correct_random_answers_open_password_reset():
    user = SimpleNamespace(id=7, username="Satya", role="SUPER_ADMIN", is_active=True)
    questions = [
        SimpleNamespace(id=11, user_id=7, question="School?", answer_hash=hash_password("school"), is_active=True),
        SimpleNamespace(id=22, user_id=7, question="City?", answer_hash=hash_password("city"), is_active=True),
    ]
    request = _request({
        password_recovery.RECOVERY_SESSION_USER: 7,
        password_recovery.RECOVERY_SESSION_EXPIRES: 9999999999,
        password_recovery.RECOVERY_SESSION_QUESTIONS: [11, 22],
    })

    class FakeDB:
        def get(self, _model, user_id):
            return user if user_id == 7 else None

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: questions)

    response = password_recovery.verify_recovery(request, "school", "city", FakeDB())
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/super-admin/forgot-password/reset"
    assert request.session["super_admin_recovery_verified"] is True


def test_wrong_answer_closes_recovery_session():
    user = SimpleNamespace(id=7, username="Satya", role="SUPER_ADMIN", is_active=True)
    questions = [SimpleNamespace(id=11, user_id=7, question="School?", answer_hash=hash_password("school"), is_active=True), SimpleNamespace(id=22, user_id=7, question="City?", answer_hash=hash_password("city"), is_active=True)]
    request = _request({
        password_recovery.RECOVERY_SESSION_USER: 7,
        password_recovery.RECOVERY_SESSION_EXPIRES: 9999999999,
        password_recovery.RECOVERY_SESSION_QUESTIONS: [11, 22],
    })

    class FakeDB:
        def get(self, _model, user_id):
            return user if user_id == 7 else None

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: questions)

    response = password_recovery.verify_recovery(request, "wrong", "city", FakeDB())
    assert response.status_code == 200
    assert request.session == {}
    assert b"incorrect" in response.body


def test_password_reset_changes_password_and_invalidates_sessions():
    user = SimpleNamespace(id=7, role="SUPER_ADMIN", is_active=True, password_hash=hash_password("OldPassword123"), session_version=4)
    request = _request({
        password_recovery.RECOVERY_SESSION_USER: 7,
        password_recovery.RECOVERY_SESSION_EXPIRES: 9999999999,
        "super_admin_recovery_verified": True,
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


def test_password_reset_rejects_mismatched_passwords():
    user = SimpleNamespace(id=7, role="SUPER_ADMIN", is_active=True, password_hash=hash_password("OldPassword123"), session_version=4)
    request = _request({
        password_recovery.RECOVERY_SESSION_USER: 7,
        password_recovery.RECOVERY_SESSION_EXPIRES: 9999999999,
        "super_admin_recovery_verified": True,
    })

    class FakeDB:
        def get(self, _model, user_id):
            return user if user_id == 7 else None

    response = password_recovery.reset_password(request, "NewPassword123", "DifferentPassword123", FakeDB())
    assert response.status_code == 200
    assert verify_password("OldPassword123", user.password_hash)
    assert user.session_version == 4


def test_security_questions_save_requires_all_five_answers():
    user = SimpleNamespace(id=7, role="SUPER_ADMIN", is_active=True)
    request = _request({"user_id": 7, "login_portal": "super_admin"})

    class FakeDB:
        def get(self, _model, user_id):
            return user if user_id == 7 else None

    response = password_recovery.save_security_questions(request, "a", "b", "", "d", "e", FakeDB())
    assert response.status_code == 200
    assert b"all five" in response.body
