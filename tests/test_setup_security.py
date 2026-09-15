from app.setup_security import validate_setup_credentials


def test_setup_rejects_short_password_server_side():
    assert validate_setup_credentials("admin", "short", "Question", "Answer") == "password_too_short"


def test_setup_rejects_empty_username_server_side():
    assert validate_setup_credentials("   ", "long-enough", "Question", "Answer") == "invalid_username"


def test_setup_accepts_valid_bootstrap_credentials():
    assert validate_setup_credentials("superadmin", "long-enough-password", "Question", "Answer") is None
