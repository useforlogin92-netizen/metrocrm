from datetime import datetime, timedelta, timezone

from app.property_submission_models import PropertySubmission
from app.routers.property_submissions import (
    MAX_PLAN_UPLOAD_BYTES,
    MAX_PLAN_VIDEO_BYTES,
    _normalise_configuration_details,
    _plan_magic_ok,
    _plan_video_magic_ok,
    _token_hash,
    _valid,
)


def test_submission_tokens_are_hashed_and_links_are_not_reversible():
    token = "sample-secure-token"
    digest = _token_hash(token)
    assert len(digest) == 64
    assert digest != token
    assert digest == _token_hash(token)


def test_submission_link_is_editable_only_before_submission_or_after_correction_request():
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    row = PropertySubmission(id=1, token_hash="x", created_by_id=1, recipient_name="SM", expires_at=future, status="OPEN")
    assert _valid(row) is True
    row.status = "SUBMITTED"
    assert _valid(row) is False
    row.status = "CORRECTION_REQUESTED"
    assert _valid(row) is True
    row.status = "IMPORTED"
    assert _valid(row) is False
    row.status = "CORRECTION_REQUESTED"
    row.revoked = True
    assert _valid(row) is False


def test_expired_submission_is_invalid():
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    row = PropertySubmission(id=1, token_hash="x", created_by_id=1, recipient_name="SM", expires_at=past, status="OPEN")
    assert _valid(row) is False


def test_configuration_rows_can_repeat_same_bhk_with_different_details_and_plan_chart_and_video():
    details = _normalise_configuration_details(
        ["1 BHK", "1 BHK", "2 BHK"],
        ["350", "400.45", "750"],
        ["12000", "12500", "11000"],
        ["4200000", "5005625", "8250000"],
        ["Yes", "No", "Yes"],
        ["Available", "Limited", "Available"],
        ["4", "2", "3"],
        ["A", "A", "B"],
        ["8", "9", "10"],
        ["1 covered", "1 covered", "2 covered"],
        ["", "", ""],
        ["data:image/png;base64,AAA", "data:application/pdf;base64,BBB", ""],
        ["data:video/mp4;base64,AAA", "", "data:video/webm;base64,BBB"],
    )
    assert [item["configuration"] for item in details] == ["1 BHK", "1 BHK", "2 BHK"]
    assert [item["carpet_area"] for item in details] == ["350", "400.45", "750"]
    assert details[0]["plan_chart"].startswith("data:image/png")
    assert details[1]["plan_chart"].startswith("data:application/pdf")
    assert details[2]["plan_chart"] == ""
    assert details[0]["plan_video"].startswith("data:video/mp4")
    assert details[2]["plan_video"].startswith("data:video/webm")


def test_plan_upload_limits_are_large_enough_for_hd_assets():
    assert MAX_PLAN_UPLOAD_BYTES == 20 * 1024 * 1024
    assert MAX_PLAN_VIDEO_BYTES == 50 * 1024 * 1024


def test_plan_magic_bytes_match_declared_type():
    assert _plan_magic_ok("application/pdf", b"%PDF-1.7\n") is True
    assert _plan_magic_ok("image/png", b"\x89PNG\r\n\x1a\nrest") is True
    assert _plan_magic_ok("image/jpeg", b"\xff\xd8\xff\xe0rest") is True
    assert _plan_magic_ok("image/webp", b"RIFFxxxxWEBPrest") is True
    assert _plan_magic_ok("image/png", b"not-a-png") is False


def test_plan_video_magic_bytes_match_declared_type():
    assert _plan_video_magic_ok("video/mp4", b"0000ftypisomrest") is True
    assert _plan_video_magic_ok("video/quicktime", b"0000ftypqt  rest") is True
    assert _plan_video_magic_ok("video/webm", b"\x1a\x45\xdf\xa3rest") is True
    assert _plan_video_magic_ok("video/mp4", b"not-a-video") is False
