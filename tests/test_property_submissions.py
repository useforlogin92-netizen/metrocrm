from datetime import datetime, timedelta, timezone

from app.property_submission_models import PropertySubmission
from app.routers.property_submissions import _token_hash, _valid


def test_submission_tokens_are_hashed_and_links_are_not_reversible():
    token = "sample-secure-token"
    digest = _token_hash(token)
    assert len(digest) == 64
    assert digest != token
    assert digest == _token_hash(token)


def test_submission_link_is_valid_until_expiry_and_rejects_revoked_or_submitted():
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    row = PropertySubmission(id=1, token_hash="x", created_by_id=1, recipient_name="SM", expires_at=future, status="OPEN")
    assert _valid(row) is True
    row.revoked = True
    assert _valid(row) is False
    row.revoked = False
    row.status = "SUBMITTED"
    assert _valid(row) is False


def test_expired_submission_is_invalid():
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    row = PropertySubmission(id=1, token_hash="x", created_by_id=1, recipient_name="SM", expires_at=past, status="OPEN")
    assert _valid(row) is False
