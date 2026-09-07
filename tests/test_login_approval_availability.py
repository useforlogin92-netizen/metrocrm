from app.models import User
from app.portal import _has_other_active_super_admin


def test_approval_requires_another_active_super_admin(db_session):
    admin = User(username="admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add(admin)
    db_session.flush()
    assert _has_other_active_super_admin(db_session, admin.id) is False

    super_admin = User(username="sa", password_hash="x", role="SUPER_ADMIN", is_active=True, is_approved=True)
    db_session.add(super_admin)
    db_session.commit()
    assert _has_other_active_super_admin(db_session, admin.id) is True
