from types import SimpleNamespace

from app.routers.whatsapp_property_import import _can_access


def user(role: str, user_id: int):
    return SimpleNamespace(role=role, id=user_id)


def submission(created_by_id: int):
    return SimpleNamespace(created_by_id=created_by_id)


def test_super_admin_can_access_any_import():
    assert _can_access(submission(99), user("SUPER_ADMIN", 1)) is True


def test_admin_can_access_only_own_import():
    actor = user("ADMIN", 7)
    assert _can_access(submission(7), actor) is True
    assert _can_access(submission(8), actor) is False


def test_non_admin_roles_cannot_access_property_import():
    for role in ("MANAGER", "SALES", "STAFF", "USER"):
        assert _can_access(submission(7), user(role, 7)) is False
