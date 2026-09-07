from app.auth import create_pending, pending_method, verify_pending
from app.email_verification import EmailVerification
from app.models import User
from app.security import hash_password


def make_user(db_session, *, approved=False, email="user@example.com"):
    user = User(
        username="test-user",
        password_hash=hash_password("StrongPassword123!"),
        role="SALES",
        email=email,
        is_active=True,
        is_approved=approved,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_approval_challenge_can_be_created_before_login_approval(db_session):
    user = make_user(db_session, approved=False)
    token, challenge = create_pending(user, "approval")
    assert pending_method(token) == "approval"
    assert challenge is None
    assert verify_pending(token, "APPROVED", 300, 5) == user.id


def test_approved_account_can_complete_approval_challenge(db_session):
    user = make_user(db_session, approved=True)
    token, challenge = create_pending(user, "approval")
    assert pending_method(token) == "approval"
    assert challenge is None
    assert verify_pending(token, "APPROVED", 300, 5) == user.id


def test_email_verification_is_independent_from_admin_approval(db_session):
    user = make_user(db_session, approved=False)
    db_session.add(EmailVerification(user_id=user.id))
    db_session.commit()
    assert user.is_approved is False
    assert db_session.query(EmailVerification).filter_by(user_id=user.id).one() is not None
