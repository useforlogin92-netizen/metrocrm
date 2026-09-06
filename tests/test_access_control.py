from app.access_control import mask_email, mask_phone, sanitize_record, visibility_for_field
from app.permissions import FieldVisibility, Role


def test_mask_phone():
    assert mask_phone("9876543210") == "98XXXXXX10"


def test_mask_email():
    assert mask_email("person@example.com") == "pXXXXXX@example.com"


def test_sensitive_fields_are_masked_for_sales():
    assert visibility_for_field(Role.SALES_EXECUTIVE, "mobile") == FieldVisibility.MASKED
    assert visibility_for_field(Role.SALES_EXECUTIVE, "email") == FieldVisibility.MASKED
    assert visibility_for_field(Role.SALES_EXECUTIVE, "name") == FieldVisibility.VIEW


def test_admin_can_view_sensitive_fields_by_default():
    assert visibility_for_field(Role.ADMIN, "mobile") == FieldVisibility.VIEW
    assert visibility_for_field(Role.MANAGER, "email") == FieldVisibility.VIEW


def test_hidden_field_is_removed_and_masked_field_is_sanitized():
    record = {"name": "Test Customer", "mobile": "9876543210", "email": "person@example.com"}
    masked = sanitize_record(Role.SALES_EXECUTIVE, record)
    assert masked["name"] == "Test Customer"
    assert masked["mobile"] == "98XXXXXX10"
    assert masked["email"] == "pXXXXXX@example.com"
