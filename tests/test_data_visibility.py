from app.services.data_visibility import mask_email, mask_mobile, sanitize_record


def test_mobile_is_masked():
    assert mask_mobile("9876543210") == "98XXXXXX10"


def test_email_is_masked():
    assert mask_email("krishna@example.com") == "kXXXXXXXXXXXXXXXX@example.com"


def test_hidden_sensitive_fields_are_not_returned():
    record = {"name": "Test Customer", "mobile": "9876543210", "budget_max": 5000000}
    safe = sanitize_record(record, {"mobile": "MASKED", "budget_max": "HIDDEN"})
    assert safe["name"] == "Test Customer"
    assert safe["mobile"] == "98XXXXXX10"
    assert safe["budget_max"] is None


def test_unknown_fields_remain_visible():
    safe = sanitize_record({"name": "Test", "source": "Website"})
    assert safe == {"name": "Test", "source": "Website"}
