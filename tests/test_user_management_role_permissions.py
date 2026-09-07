from app.main import _can_manage_user, _valid_reporting_manager
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


def test_invalid_role_is_never_manageable():
    assert _can_manage_user(_user(1, "SUPER_ADMIN"), target_role="ROOT") is False
    assert _can_manage_user(_user(1, "ADMIN"), target_role="ROOT") is False


def test_reporting_manager_validation_rejects_inactive_non_management_and_self(db_session):
    actor = _user(1, "SUPER_ADMIN")
    target = _user(2, "MANAGER")
    inactive = _user(3, "MANAGER")
    inactive.is_active = False
    sales = _user(4, "SALES_EXECUTIVE")
    db_session.add_all([actor, target, inactive, sales])
    db_session.commit()
    assert _valid_reporting_manager(actor, None, target, db_session) is True
    assert _valid_reporting_manager(actor, target.id, target, db_session) is False
    assert _valid_reporting_manager(actor, inactive.id, target, db_session) is False
    assert _valid_reporting_manager(actor, sales.id, target, db_session) is False


def test_admin_cannot_assign_super_admin_as_reporting_manager(db_session):
    actor = _user(1, "ADMIN")
    target = _user(2, "MANAGER")
    super_admin = _user(3, "SUPER_ADMIN")
    db_session.add_all([actor, target, super_admin])
    db_session.commit()
    assert _valid_reporting_manager(actor, super_admin.id, target, db_session) is False
