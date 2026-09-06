from app.access_control import mask_email, mask_phone, sanitize_record, visibility_for_field
from app.permissions import Access, FieldVisibility, Role, can_assign_lead, can_direct_delete, can_direct_export, effective_access


def test_assignment_is_management_only_by_default():
    assert can_assign_lead(Role.SUPER_ADMIN)
    assert can_assign_lead(Role.ADMIN)
    assert can_assign_lead(Role.MANAGER)
    assert not can_assign_lead(Role.TL)
    assert not can_assign_lead(Role.SALES_EXECUTIVE)
    assert not can_assign_lead(Role.TELECALLER)


def test_user_restriction_overrides_role_default():
    access = effective_access(Role.MANAGER, denies={Access.ASSIGN})
    assert Access.ASSIGN not in access


def test_export_and_delete_are_not_direct_for_admin():
    assert can_direct_export(Role.SUPER_ADMIN)
    assert can_direct_delete(Role.SUPER_ADMIN)
    assert not can_direct_export(Role.ADMIN)
    assert not can_direct_delete(Role.ADMIN)
    assert not can_direct_export(Role.SALES_EXECUTIVE)


def test_sensitive_fields_are_masked_for_sales_roles():
    assert visibility_for_field(Role.SALES_EXECUTIVE, "mobile") == FieldVisibility.MASKED
    assert visibility_for_field(Role.SALES_EXECUTIVE, "email") == FieldVisibility.MASKED
    assert visibility_for_field(Role.SALES_EXECUTIVE, "name") == FieldVisibility.VIEW


def test_phone_and_email_masking():
    assert mask_phone("9876543210") == "98XXXXXX10"
    assert mask_email("person@example.com") == "pXXXXXX@example.com"


def test_sanitize_record_applies_field_policy():
    record = {"name": "Test Customer", "mobile": "9876543210", "email": "person@example.com", "internal_notes": "private"}
    safe = sanitize_record(Role.SALES_EXECUTIVE, record)
    assert safe["name"] == "Test Customer"
    assert safe["mobile"] == "98XXXXXX10"
    assert safe["email"] == "pXXXXXX@example.com"
    assert safe["internal_notes"] == "••••••"


def test_user_specific_hidden_override_is_respected():
    record = {"name": "Test Customer", "mobile": "9876543210"}
    safe = sanitize_record(Role.ADMIN, record, {"mobile": "HIDDEN"})
    assert "mobile" not in safe
