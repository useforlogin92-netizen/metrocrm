"""Exotel API adapter for MetroCRM; never enabled implicitly.

The caller is dialled first, then the customer, with the provider-assigned
virtual number as caller ID. This avoids exposing the agent's mobile to the
customer; it does not make the agent's number private from the provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings


class TelephonyNotConfigured(RuntimeError):
    """Raised when live calling is requested without complete provider setup."""


class TelephonyProviderError(RuntimeError):
    """Raised when the provider rejects or cannot accept a call request."""


@dataclass(frozen=True)
class ExotelCall:
    provider_call_id: str
    status: str


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _validate_config() -> tuple[str, str, str, str, str, str]:
    required = {
        "EXOTEL_API_KEY": settings.exotel_api_key,
        "EXOTEL_API_TOKEN": settings.exotel_api_token,
        "EXOTEL_ACCOUNT_SID": settings.exotel_account_sid,
        "EXOTEL_VIRTUAL_NUMBER": settings.exotel_virtual_number,
        "EXOTEL_AGENT_NUMBER": settings.exotel_agent_number,
        "EXOTEL_APP_FLOW_URL": settings.exotel_app_flow_url,
    }
    missing = [key for key, value in required.items() if not value.strip()]
    if missing:
        raise TelephonyNotConfigured(
            "Exotel setup incomplete; missing: " + ", ".join(missing)
        )

    base = settings.exotel_api_base_url.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname not in {
        "api.in.exotel.com", "api.exotel.com"
    }:
        raise TelephonyNotConfigured("Exotel API base URL must be an approved HTTPS endpoint")
    if urlparse(settings.exotel_app_flow_url).scheme != "https":
        raise TelephonyNotConfigured("Exotel app/flow URL must use HTTPS")
    return (
        settings.exotel_api_key.strip(),
        settings.exotel_api_token.strip(),
        settings.exotel_account_sid.strip(),
        settings.exotel_virtual_number.strip(),
        settings.exotel_agent_number.strip(),
        base,
    )


def initiate_call(\n    customer_number: str, *, status_callback: str | None = None, timeout_seconds: float = 15.0\n) -> ExotelCall:
    """Request an Exotel two-leg call. Only invoke when provider mode is explicitly exotel."""
    api_key, api_token, sid, virtual_number, agent_number, base = _validate_config()
    customer_digits = _digits(customer_number)
    agent_digits = _digits(agent_number)
    if len(customer_digits) < 10 or len(agent_digits) < 10:
        raise ValueError("Agent and customer numbers must contain at least 10 digits")

    endpoint = f"{base}/v1/Accounts/{sid}/Calls/connect"
    form = {
        "From": agent_number,
        "To": customer_number,
        "CallerId": virtual_number,
        "Url": settings.exotel_app_flow_url.strip(),
    }
    try:
        response = httpx.post(
            endpoint,
            data=form,
            auth=(api_key, api_token),
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise TelephonyProviderError("Exotel request failed; check provider connectivity") from exc

    if response.status_code < 200 or response.status_code >= 300:
        # Do not include provider response bodies; they may contain phone numbers or metadata.
        raise TelephonyProviderError(f"Exotel rejected the call request (HTTP {response.status_code})")

    try:
        payload = response.json()
        call = payload.get("Call", payload)
        call_id = str(call.get("Sid") or call.get("CallSid") or "").strip()
        status = str(call.get("Status") or "queued").strip().lower()
    except (ValueError, AttributeError, TypeError) as exc:
        raise TelephonyProviderError("Exotel returned an unexpected response") from exc
    if not call_id:
        raise TelephonyProviderError("Exotel response did not contain a call ID")
    return ExotelCall(provider_call_id=call_id, status=status)
