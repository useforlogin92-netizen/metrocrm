from app.main import _can_manage_user
from app.models import User


def _user(user_id: int, role: str) -> User:
    return User(id=user_id, username=f"user_{user_id}", role=role, is_active=True, is_approved=True)


def test_super_admin_can_manage_super_admin_and_admin_roles():
    actor = _user(1, "SUPER_ADMIN")
    assert _can_manage_user(actor, target_role="SUPER_ADMIN") is True
    assert _can_manage_user(actor, target_role="ADMIN") is True


def test_admin_cannot_create_or_promote_to_admin_roles():
    actor = _user(1, "ADMIN")
    assert _can_manage_user(actor, target_role="SUPER_ADMIN") is False
    assert _can_manage_user(actor, target_role="ADMIN") is False


def test_admin_can_manage_lower_level_roles():
    actor = _user(1, "ADMIN")
    for role in ("MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER", "ACCOUNTANT", "HR"):
        assert _can_manage_user(actor, target_role=role) is True


def test_admin_cannot_edit_existing_admin_or_super_admin():
    actor = _user(1, "ADMIN")
    super_admin = _user(2, "SUPER_ADMIN")
    admin = _user(3, "ADMIN")
    assert _can_manage_user(actor, super_admin, target_role="MANAGER") is False
    assert _can_manage_user(actor, admin, target_role="MANAGER") is False


def test_super_admin_cannot_demote_self():
    actor = _user(1, "SUPER_ADMIN")
    assert _can_manage_user(actor, actor, target_role="ADMIN") is False
    assert _can_manage_user(actor, actor, target_role="SUPER_ADMIN") is True
