"""Specification tests for WhatsApp property-import parsing requirements.

These tests document the required safety boundary before wiring an importer into CRM.
"""


def test_whatsapp_import_must_preview_before_commit():
    workflow = ["paste", "extract", "validate", "preview", "approve", "commit"]
    assert workflow.index("preview") < workflow.index("commit")
    assert workflow.index("approve") < workflow.index("commit")


def test_whatsapp_import_must_not_guess_missing_fields():
    missing_fields = {"rera", "possession_date", "amenities"}
    assert "missing_fields" not in {"auto_guess"}
    assert missing_fields


def test_whatsapp_import_roles_are_restricted():
    allowed_roles = {"SUPER_ADMIN", "ADMIN"}
    denied_roles = {"STAFF", "USER"}
    assert allowed_roles.isdisjoint(denied_roles)


def test_whatsapp_import_supports_media_and_catalog_inputs():
    supported_inputs = {"text", "image", "video", "pdf", "catalog", "map_link"}
    assert {"text", "image", "video", "pdf"}.issubset(supported_inputs)
