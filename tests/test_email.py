from app.config import settings
from app.services.email import send_email


def test_email_provider_test_mode_does_not_claim_delivery(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "email_provider", "test")
    result = send_email("customer@example.com", "Property details", "Test message")
    assert result["status"] == "TEST"
    assert result["provider"] == "test"


def test_email_provider_rejects_invalid_destination():
    import pytest

    with pytest.raises(ValueError, match="invalid_email_destination"):
        send_email("not-an-email", "Property details", "Test message")


def test_email_provider_rejects_empty_subject_or_body():
    import pytest

    with pytest.raises(ValueError, match="email_subject_required"):
        send_email("customer@example.com", " ", "Body")
    with pytest.raises(ValueError, match="email_body_required"):
        send_email("customer@example.com", "Subject", " ")
