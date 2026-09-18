from app.services import integration_secrets


def test_integration_credentials_round_trip(monkeypatch):
    monkeypatch.setattr(integration_secrets.settings, "secret_key", "test-secret-key")
    payload = {"api_key": "key-123", "api_secret": "secret-456"}
    encrypted = integration_secrets.encrypt_credentials(payload)

    assert encrypted != str(payload)
    assert integration_secrets.decrypt_credentials(encrypted) == payload


def test_integration_credentials_invalid_value_returns_empty(monkeypatch):
    monkeypatch.setattr(integration_secrets.settings, "secret_key", "test-secret-key")
    assert integration_secrets.decrypt_credentials("not-a-valid-token") == {}
