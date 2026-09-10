"""Provider-agnostic WhatsApp delivery with safe test mode and audit metadata."""
from __future__ import annotations
import hashlib
import hmac
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from app.config import settings


def normalize_mobile(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        raise ValueError("valid_mobile_required")
    if len(digits) == 10:
        digits = "91" + digits
    if len(digits) < 11 or len(digits) > 15:
        raise ValueError("invalid_mobile_length")
    return digits


def destination_hash(mobile: str) -> str:
    return hashlib.sha256((settings.secret_key + normalize_mobile(mobile)).encode()).hexdigest()


def build_text_payload(mobile: str, body: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": normalize_mobile(mobile),
        "type": "text",
        "text": {"preview_url": True, "body": body[:4096]},
    }


def send_text(mobile: str, body: str) -> dict[str, Any]:
    payload = build_text_payload(mobile, body)
    if settings.whatsapp_mode != "live" or not settings.whatsapp_enabled:
        return {"status": "TEST", "provider": "whatsapp_cloud", "payload": payload}
    if not settings.whatsapp_api_url or not settings.whatsapp_access_token:
        raise RuntimeError("whatsapp_provider_not_configured")
    request = UrlRequest(
        settings.whatsapp_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.whatsapp_access_token}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = getattr(response, "status", 200)
            raw = response.read().decode("utf-8", errors="replace")
            if status < 200 or status >= 300:
                raise RuntimeError(f"whatsapp_delivery_http_{status}")
            data = json.loads(raw) if raw else {}
            messages = data.get("messages") or []
            return {"status": "SENT", "provider": "whatsapp_cloud", "provider_message_id": (messages[0].get("id") if messages else None), "http_status": status}
    except HTTPError as exc:
        raise RuntimeError(f"whatsapp_delivery_http_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("whatsapp_delivery_network_error") from exc


def build_property_message(property_data: dict[str, Any], share_url: str | None = None) -> str:
    labels = (
        ("Project", property_data.get("project_name")),
        ("Unit", property_data.get("unit_number")),
        ("Type", property_data.get("property_type") or property_data.get("bhk")),
        ("Area", property_data.get("carpet_area")),
        ("Price", property_data.get("price")),
        ("Location", property_data.get("location")),
        ("Possession", property_data.get("possession")),
        ("RERA", property_data.get("rera")),
    )
    lines = [f"{label}: {value}" for label, value in labels if value not in (None, "")]
    if share_url:
        lines.append(f"View property details: {share_url}")
    return "MetroCRM Property Details\n\n" + "\n".join(lines)
