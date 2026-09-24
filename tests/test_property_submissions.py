from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.property_submission_models import PropertySubmission
from app.routers.property_submissions import (
    MAX_PLAN_UPLOAD_BYTES,
    MAX_PLAN_VIDEO_BYTES,
    MAX_SM_VISITING_CARD_BYTES,
    _normalise_configuration_details,
    _normalise_name,
    _normalise_phone,
    _plan_magic_ok,
    _plan_video_magic_ok,
    _preserve_existing_uploads,
    _token_hash,
    _valid,
    _visiting_card_magic_ok,
)

ROOT = Path(__file__).parents[1]


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
    assert MAX_SM_VISITING_CARD_BYTES == 5 * 1024 * 1024


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


def test_sm_identity_normalisation_supports_name_spacing_and_indian_phone_formats():
    assert _normalise_name("  Rahul   Sharma ") == "rahul sharma"
    assert _normalise_name("Rahul Sharma") == "rahul sharma"
    assert _normalise_phone("+91 98765-43210") == "9876543210"
    assert _normalise_phone("9876543210") == "9876543210"
    assert _normalise_phone("+91-98765-43210") == "9876543210"


def test_sm_visiting_card_magic_bytes_match_declared_type():
    assert _visiting_card_magic_ok("application/pdf", b"%PDF-1.7\ncard") is True
    assert _visiting_card_magic_ok("image/png", b"\x89PNG\r\n\x1a\ncard") is True
    assert _visiting_card_magic_ok("image/jpeg", b"\xff\xd8\xff\xe0card") is True
    assert _visiting_card_magic_ok("image/webp", b"RIFFxxxxWEBPcard") is True
    assert _visiting_card_magic_ok("image/png", b"not-an-image") is False


def test_correction_preserves_previous_plan_and_video_when_replacement_is_blank():
    old = [{"configuration": "1 BHK", "carpet_area": "350", "plan_chart": "old-chart", "plan_video": "old-video"}]
    new = [{"configuration": "1 BHK", "carpet_area": "350", "plan_chart": "", "plan_video": ""}]
    result = _preserve_existing_uploads(new, old)
    assert result[0]["plan_chart"] == "old-chart"
    assert result[0]["plan_video"] == "old-video"


def test_admin_and_super_admin_both_expose_sm_property_submission_actions():
    dashboard = (ROOT / "app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    management = (ROOT / "app" / "templates" / "property_submissions_admin.html").read_text(encoding="utf-8")
    router = (ROOT / "app" / "routers" / "property_submissions.py").read_text(encoding="utf-8")
    assert "role in ['SUPER_ADMIN','ADMIN']" in dashboard
    assert "/super-admin/property-submissions" in dashboard
    assert "/admin/property-submissions" in dashboard
    assert "portal=='admin'" in management
    assert "portal=='super-admin'" in management
    assert "action=\"/admin/property-submissions/" in management
    assert "action=\"/super-admin/property-submissions/" in management
    assert '@router.get("/admin/property-submissions"' in router
    assert '@router.get("/super-admin/property-submissions"' in router
    assert '@router.get("/admin/property-submissions/new"' in router
    assert '@router.get("/super-admin/property-submissions/new"' in router


def test_single_admin_or_super_admin_approval_imports_and_locks_link():
    router = (ROOT / "app" / "routers" / "property_submissions.py").read_text(encoding="utf-8")
    assert 'if submission.status != "SUBMITTED" or submission.revoked:' in router
    assert "_import_submission(db, actor, submission, role)" in router
    assert 'submission.status = "IMPORTED"' in router
    assert "submission.revoked = True" in router
    assert 'if submission.admin_approved_by and submission.super_admin_approved_by' not in router


def test_sm_identity_is_required_and_verified_before_property_submission():
    router = (ROOT / "app" / "routers" / "property_submissions.py").read_text(encoding="utf-8")
    assert 'submitted_sm_name = str(form.get("sm_name", "")).strip()' in router
    assert 'submitted_sm_contact = str(form.get("sm_contact", "")).strip()' in router
    assert '_normalise_name(submitted_sm_name) != _normalise_name(submission.recipient_name)' in router
    assert 'expected_phone = _normalise_phone(submission.recipient_mobile or "")' in router
    assert 'actual_phone = _normalise_phone(submitted_sm_contact)' in router


def test_sm_visiting_card_is_optional_but_validated_and_preserved():
    router = (ROOT / "app" / "routers" / "property_submissions.py").read_text(encoding="utf-8")
    form = (ROOT / "app" / "templates" / "property_submission.html").read_text(encoding="utf-8")
    assert "MAX_SM_VISITING_CARD_BYTES = 5 * 1024 * 1024" in router
    assert "_normalise_visiting_card" in router
    assert 'name="sm_visiting_card"' in form
    assert "Optional" in form


def test_correction_request_uses_fresh_token_and_records_admin_filled_fields():
    from app.routers.property_submissions import _request_correction
    from app.models import User
    user = User(username="correction-admin", password_hash="hash", role="ADMIN", is_active=True, is_approved=True)
    db = None
    # This contract is covered by the source-level behavior and token hashing rules.
    router = (ROOT / "app" / "routers" / "property_submissions.py").read_text(encoding="utf-8")
    assert "new_token = secrets.token_urlsafe(32)" in router
    assert 'submission.token_hash = _token_hash(new_token)' in router
    assert '"admin_filled_fields"' in router
    assert 'payload["latest_correction_request"] = reason' in router
