from app.integrations.intake import payload_fingerprint, verify_hmac_signature, prepare_external_lead


def test_external_lead_intake_normalizes_and_fingerprints():
    payload = {"id": "lead-1", "full_name": "Test", "phone": "9999999999"}
    lead, fingerprint = prepare_external_lead("meta_ads", payload)
    assert lead.external_id == "lead-1"
    assert lead.source == "meta_ads"
    assert fingerprint == payload_fingerprint(payload)


def test_webhook_hmac_signature_is_verified():
    payload = b'{"id":"lead-1"}'
    import hmac, hashlib
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    assert verify_hmac_signature(payload, signature, "secret")
    assert not verify_hmac_signature(payload, "bad", "secret")
