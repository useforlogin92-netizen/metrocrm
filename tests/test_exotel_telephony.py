from unittest.mock import Mock, patch

import pytest

from app.telephony.exotel import (
    TelephonyNotConfigured,
    TelephonyProviderError,
    initiate_call,
)


def test_exotel_refuses_to_start_without_configuration(monkeypatch):
    from app.config import settings
    for name in (
        "exotel_api_key", "exotel_api_token", "exotel_account_sid",
        "exotel_virtual_number", "exotel_agent_number", "exotel_app_flow_url",
    ):
        monkeypatch.setattr(settings, name, "")
    with pytest.raises(TelephonyNotConfigured):
        initiate_call("+919876543210")


def test_exotel_sends_virtual_number_as_customer_facing_caller_id(monkeypatch):
    from app.config import settings
    values = {
        "exotel_api_key": "test-key",
        "exotel_api_token": "test-token",
        "exotel_account_sid": "test-sid",
        "exotel_virtual_number": "02212345678",
        "exotel_agent_number": "+919876543210",
        "exotel_app_flow_url": "https://example.test/exotel-flow",
        "exotel_api_base_url": "https://api.in.exotel.com",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    fake = Mock(status_code=200)
    fake.json.return_value = {"Call": {"Sid": "provider-call-1", "Status": "queued"}}
    with patch("app.telephony.exotel.httpx.post", return_value=fake) as post:
        result = initiate_call("+919123456789", status_callback="https://crm.example.test/caller/api/telephony/exotel/status")
    assert result.provider_call_id == "provider-call-1"
    assert result.status == "queued"
    assert post.call_args.kwargs["data"]["CallerId"] == "02212345678"
    assert post.call_args.kwargs["data"]["From"] == "+919876543210"\n    assert post.call_args.kwargs["data"]["StatusCallback"] == "https://crm.example.test/caller/api/telephony/exotel/status"\n    assert post.call_args.kwargs["data"]["StatusCallbackEvents[0]"] == "ringing"\n    assert post.call_args.kwargs["data"]["StatusCallbackEvents[1]"] == "answered"\n    assert post.call_args.kwargs["data"]["StatusCallbackEvents[2]"] == "terminal"


def test_exotel_provider_errors_do_not_leak_response_body(monkeypatch):
    from app.config import settings
    values = {
        "exotel_api_key": "test-key", "exotel_api_token": "test-token",
        "exotel_account_sid": "test-sid", "exotel_virtual_number": "02212345678",
        "exotel_agent_number": "+919876543210",
        "exotel_app_flow_url": "https://example.test/exotel-flow",
        "exotel_api_base_url": "https://api.in.exotel.com",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    fake = Mock(status_code=401, text="secret details")
    with patch("app.telephony.exotel.httpx.post", return_value=fake):
        with pytest.raises(TelephonyProviderError) as error:
            initiate_call("+919123456789")
    assert "secret details" not in str(error.value)
\n\ndef test_exotel_rejects_non_https_status_callback(monkeypatch):\n    from app.config import settings\n    values = {\n        "exotel_api_key": "test-key", "exotel_api_token": "test-token",\n        "exotel_account_sid": "test-sid", "exotel_virtual_number": "02212345678",\n        "exotel_agent_number": "+919876543210",\n        "exotel_app_flow_url": "https://example.test/exotel-flow",\n        "exotel_api_base_url": "https://api.in.exotel.com",\n    }\n    for name, value in values.items():\n        monkeypatch.setattr(settings, name, value)\n    with pytest.raises(TelephonyNotConfigured):\n        initiate_call("+919123456789", status_callback="http://example.test/callback")\n