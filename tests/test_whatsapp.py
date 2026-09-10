from types import SimpleNamespace

from app.main_portal import app
from app.config import settings
from app.services import whatsapp


def test_whatsapp_routes_are_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/whatsapp" in paths
    assert "/whatsapp/send" in paths
    assert "/whatsapp/property-share" in paths


def test_mobile_normalization_accepts_indian_ten_digit_number():
    assert whatsapp.normalize_mobile("98765 43210") == "919876543210"
    assert whatsapp.normalize_mobile("+91-9876543210") == "919876543210"


def test_mobile_normalization_rejects_invalid_length():
    try:
        whatsapp.normalize_mobile("12345")
    except ValueError as exc:
        assert str(exc) == "invalid_mobile_length"
    else:
        raise AssertionError("invalid mobile should be rejected")


def test_text_payload_is_provider_neutral_and_bounded():
    payload = whatsapp.build_text_payload("9876543210", "Hello")
    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "919876543210"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "Hello"
    assert len(whatsapp.build_text_payload("9876543210", "x" * 5000)["text"]["body"]) == 4096


def test_test_mode_never_calls_external_provider(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_mode", "test")
    monkeypatch.setattr(settings, "whatsapp_enabled", False)
    result = whatsapp.send_text("9876543210", "Test message")
    assert result["status"] == "TEST"
    assert result["payload"]["to"] == "919876543210"


def test_property_message_contains_selected_core_details():
    body = whatsapp.build_property_message({"project_name": "Metro Heights", "unit_number": "A-1204", "bhk": "2 BHK", "price": "12000000", "location": "Andheri"}, "https://crm.example/catalog/view/token")
    assert "Metro Heights" in body
    assert "A-1204" in body
    assert "2 BHK" in body
    assert "https://crm.example/catalog/view/token" in body
