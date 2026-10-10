"""Controlled outbound email delivery for MetroCRM.

Production sends require the configured JSON email gateway. Test/non-production
mode returns TEST and never claims that a message reached the customer.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from app.config import settings


def send_email(destination: str, subject: str, body: str) -> dict:
    recipient = (destination or "").strip()
    if not recipient or "@" not in recipient or recipient.startswith("@") or recipient.endswith("@"):
        raise ValueError("invalid_email_destination")
    if not subject.strip():
        raise ValueError("email_subject_required")
    if not body.strip():
        raise ValueError("email_body_required")

    provider = (settings.email_provider or "test").strip().lower()
    if provider == "test" or settings.environment != "production":
        return {"status": "TEST", "provider": provider, "destination": recipient}

    if not settings.email_api_url or not settings.email_api_key or not settings.email_from:
        raise RuntimeError("email_provider_not_configured")

    payload = {"to": recipient, "subject": subject.strip(), "body": body.strip(), "from": settings.email_from}
    request = UrlRequest(
        settings.email_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.email_api_key}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise RuntimeError(f"email_delivery_http_{status}")
            return {"status": "SENT", "provider": provider, "http_status": status}
    except HTTPError as exc:
        raise RuntimeError(f"email_delivery_http_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("email_delivery_network_error") from exc
