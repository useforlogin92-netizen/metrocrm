import json


def test_normalize_supported_paid_and_social_lead_sources():
    from app.services.integrations import normalize_lead_payload
    for provider in ["magicbricks", "99acres", "housing", "facebook", "instagram", "google", "meta_ads", "other"]:
        result = normalize_lead_payload(provider, {"lead": {"id": "x1", "full_name": "Test", "phone": "9876543210", "location": "Borivali"}})
        assert result["source"] == provider
        assert result["name"] == "Test"
        assert result["external_lead_id"] == "x1"


def test_webhook_signature_fail_closed_in_production(monkeypatch):
    from app.config import settings
    from app.services.integrations import verify_webhook_signature
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "integration_webhook_secret", "secret")
    assert not verify_webhook_signature(b"{}", None)


def test_lead_webhook_is_idempotent(db_session, monkeypatch):
    from app.config import settings
    from app.services.integrations import ingest_lead
    monkeypatch.setattr(settings, "environment", "development")
    payload = {"lead": {"id": "same-1", "name": "A", "phone": "9999999999"}}
    raw = json.dumps(payload).encode()
    first = ingest_lead(db_session, "meta_ads", payload, raw)
    second = ingest_lead(db_session, "meta_ads", payload, raw)
    assert first.id == second.id
    assert first.lead_id == second.lead_id
    from app.models import Lead
    assert db_session.query(Lead).count() == 1
