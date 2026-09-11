import json
from datetime import datetime, timedelta, timezone

from app.models import User
from app.property_submission_models import PropertySubmission


def test_validation_retry_does_not_overwrite_last_good_payload(db_session):
    user = User(
        username="sm-owner",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
        is_approved=True,
    )
    db_session.add(user)
    db_session.flush()
    submission = PropertySubmission(
        token_hash="a" * 64,
        created_by_id=user.id,
        recipient_name="SM",
        recipient_mobile="9876543210",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        status="CORRECTION_REQUESTED",
        payload_json=json.dumps({"project_name": "Good Project", "configuration_details": [{"configuration": "1 BHK"}]}),
    )
    db_session.add(submission)
    db_session.commit()

    submission.payload_json = json.dumps({"project_name": "Incomplete", "configuration_details": []})
    db_session.commit()
    db_session.refresh(submission)

    payload = json.loads(submission.payload_json)
    assert payload["project_name"] == "Good Project"
    assert payload["configuration_details"] == [{"configuration": "1 BHK"}]


def test_real_correction_resubmission_can_replace_payload(db_session):
    user = User(
        username="sm-owner-2",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
        is_approved=True,
    )
    db_session.add(user)
    db_session.flush()
    submission = PropertySubmission(
        token_hash="b" * 64,
        created_by_id=user.id,
        recipient_name="SM",
        recipient_mobile="9876543210",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        status="CORRECTION_REQUESTED",
        payload_json=json.dumps({"project_name": "Old Project"}),
    )
    db_session.add(submission)
    db_session.commit()

    submission.payload_json = json.dumps({"project_name": "Corrected Project"})
    submission.status = "SUBMITTED"
    db_session.commit()
    db_session.refresh(submission)

    assert json.loads(submission.payload_json)["project_name"] == "Corrected Project"
