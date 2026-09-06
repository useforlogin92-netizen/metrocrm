"""Provider-agnostic lead intake and OTP delivery adapters.

Real provider credentials stay in environment variables. Webhook payloads are
normalized here so each portal/ad platform can be connected without changing
CRM lead logic later.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.integration_models import IntegrationConfig, LeadIntegrationEvent
from app.models import AuditEvent, Customer, Lead

SUPPORTED_LEAD_PROVIDERS = (
    "magicbricks", "99acres", "housing", "facebook", "instagram", "google", "meta_ads", "other"
)


def normalize_lead_payload(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Map common portal/ad fields into MetroCRM's canonical lead shape."""
    data = payload.get("lead") if isinstance(payload.get("lead"), dict) else payload
    name = data.get("name") or data.get("full_name") or data.get("customer_name") or "Unknown Lead"
    mobile = data.get("mobile") or data.get("phone") or data.get("phone_number")
    email = data.get("email") or data.get("email_address")
    return {
        "name": str(name)[:200],
        "mobile": str(mobile)[:30] if mobile else None,
        "alternate_mobile": str(data.get("alternate_mobile") or data.get("alternate_phone"))[:30] if data.get("alternate_mobile") or data.get("alternate_phone") else None,
        "email": str(email)[:255] if email else None,
        "source": provider,
        "requirement": data.get("requirement") or data.get("message") or data.get("notes"),
        "budget_min": data.get("budget_min"),
        "budget_max": data.get("budget_max") or data.get("budget"),
        "preferred_location": data.get("preferred_location") or data.get("location"),
        "bhk": data.get("bhk"),
        "property_type": data.get("property_type"),
        "buy_rent": data.get("buy_rent") or data.get("intent"),
        "external_lead_id": str(data.get("lead_id") or data.get("id") or data.get("external_id") or "")[:255] or None,
    }


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = settings.integration_webhook_secret
    if not secret:
        # Development/test mode can receive unsigned events; production should configure a secret.
        return settings.environment != "production"
    if not signature:
        return False
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def ingest_lead(db: Session, provider: str, payload: dict[str, Any], raw_body: bytes) -> LeadIntegrationEvent:
    provider = provider.lower().strip()
    if provider not in SUPPORTED_LEAD_PROVIDERS:
        raise ValueError("unsupported_lead_provider")
    normalized = normalize_lead_payload(provider, payload)
    payload_hash = hashlib.sha256(raw_body).hexdigest()

    # Idempotency is based on the provider's stable external lead ID when supplied.
    # Payload hash remains the fallback for providers/events that do not expose one.
    existing = None
    if normalized["external_lead_id"]:
        existing = db.scalar(select(LeadIntegrationEvent).where(
            LeadIntegrationEvent.provider == provider,
            LeadIntegrationEvent.external_lead_id == normalized["external_lead_id"],
        ))
    if existing is None:
        existing = db.scalar(select(LeadIntegrationEvent).where(
            LeadIntegrationEvent.provider == provider,
            LeadIntegrationEvent.payload_hash == payload_hash,
        ))
    if existing:
        return existing

    event = LeadIntegrationEvent(provider=provider, external_lead_id=normalized["external_lead_id"], payload_hash=payload_hash, payload_json=json.dumps(payload, default=str))
    db.add(event)
    customer = None
    if normalized["mobile"]:
        customer = db.scalar(select(Customer).where(Customer.mobile == normalized["mobile"]))
    if customer is None and normalized["email"]:
        customer = db.scalar(select(Customer).where(Customer.email == normalized["email"]))
    if customer is None:
        customer = Customer(name=normalized["name"], mobile=normalized["mobile"], alternate_mobile=normalized["alternate_mobile"], email=normalized["email"], notes=normalized["requirement"])
        db.add(customer); db.flush()
    lead = Lead(customer_id=customer.id, source=provider, status="NEW", assigned_user_id=None, original_owner_id=None,
                requirement=normalized["requirement"], budget_min=normalized["budget_min"], budget_max=normalized["budget_max"],
                preferred_location=normalized["preferred_location"], bhk=normalized["bhk"], property_type=normalized["property_type"], buy_rent=normalized["buy_rent"])
    db.add(lead); db.flush()
    event.lead_id = lead.id
    event.status = "PROCESSED"
    event.processed_at = datetime.utcnow()
    db.add(AuditEvent(action="EXTERNAL_LEAD_RECEIVED", entity_type="Lead", entity_id=str(lead.id), details=json.dumps({"provider": provider, "event_id": event.id})))
    db.commit()
    return event


class OtpProvider:
    """Provider abstraction. Test mode returns a code; real adapters can be added without changing auth."""
    def __init__(self, channel: str):
        self.channel = channel

    def send(self, destination: str, code: str) -> dict[str, Any]:
        provider = settings.otp_mobile_provider if self.channel == "mobile" else settings.otp_email_provider
        if provider == "test" or settings.environment != "production":
            return {"status": "TEST", "provider": provider, "destination": destination}
        # Intentionally fail closed until a configured provider adapter exists.
        raise RuntimeError(f"otp_provider_not_implemented:{provider}")


def generate_and_send_otp(channel: str, destination: str) -> tuple[str, dict[str, Any]]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    return code, OtpProvider(channel).send(destination, code)
