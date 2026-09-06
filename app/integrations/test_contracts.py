"""Small self-testable contracts for external integrations."""
from __future__ import annotations

from datetime import datetime, timedelta
from app.integrations.providers import LEAD_PROVIDERS, normalize_lead
from app.integrations.otp import OTPDeliveryProvider
from app.integrations.visitor_alerts import visitor_key, within_cooldown


def run_contract_checks() -> None:
    assert {"magicbricks", "99acres", "housing", "facebook", "instagram", "google", "meta_ads"}.issubset(LEAD_PROVIDERS)
    lead = normalize_lead("Facebook", {"id": "fb-test", "full_name": "Test", "phone": "9999999999"})
    assert lead.source == "facebook" and lead.external_id == "fb-test"
    assert OTPDeliveryProvider().send("test@example.invalid", "123456", channel="email").accepted
    assert len(visitor_key("visitor-test")) == 64
    now = datetime.utcnow()
    assert within_cooldown(now - timedelta(seconds=10), now, 60)
    assert not within_cooldown(now - timedelta(seconds=61), now, 60)
