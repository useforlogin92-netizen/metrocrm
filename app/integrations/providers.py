"""Provider-agnostic integration contracts.

Real credentials stay in environment/configuration. Provider adapters can be
implemented without changing the lead lifecycle or OTP/notification code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LEAD_PROVIDERS = (
    "magicbricks", "99acres", "housing", "facebook", "instagram",
    "google", "meta_ads", "website", "whatsapp", "other",
)
OTP_PROVIDERS = ("sms", "email")

@dataclass(slots=True)
class ProviderConfig:
    provider: str
    enabled: bool = False
    mode: str = "TEST"
    settings: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class NormalizedLead:
    source: str
    external_id: str
    name: str = ""
    mobile: str | None = None
    email: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

def normalize_lead(provider: str, payload: dict[str, Any], external_id: str | None = None) -> NormalizedLead:
    """Normalize common lead fields while preserving the original payload."""
    provider = provider.strip().lower()
    if provider not in LEAD_PROVIDERS:
        raise ValueError("unsupported_lead_provider")
    data = payload or {}
    external_id = external_id or str(data.get("lead_id") or data.get("id") or "")
    if not external_id:
        raise ValueError("external_lead_id_required")
    return NormalizedLead(
        source=provider,
        external_id=external_id,
        name=str(data.get("name") or data.get("full_name") or "").strip(),
        mobile=data.get("mobile") or data.get("phone"),
        email=data.get("email"),
        payload=data,
    )
