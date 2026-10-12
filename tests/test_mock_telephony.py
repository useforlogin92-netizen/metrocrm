from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import mock_telephony


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(mock_telephony.router)
    return TestClient(app)


def test_mock_call_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("METROCRM_ENABLE_MOCK_TELEPHONY", raising=False)
    response = _client().post(
        "/api/telephony/mock-call",
        json={"executive_id": "exec-1", "client_phone": "+91 98765 43210", "lead_name": "Test Lead"},
    )
    assert response.status_code == 404


def test_mock_call_returns_simulated_sid_and_masks_phone(monkeypatch):
    monkeypatch.setenv("METROCRM_ENABLE_MOCK_TELEPHONY", "1")
    response = _client().post(
        "/api/telephony/mock-call",
        json={"executive_id": "exec-1", "client_phone": "+91 98765 43210", "lead_name": "Test Lead"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["mock"] is True
    assert data["call_sid"].startswith("MOCK-")
    assert data["status"] == "simulated"
    assert "98765 43210" not in data["client_phone_masked"]
    assert "No real telephone call" in data["message"]


def test_mock_call_rejects_invalid_phone(monkeypatch):
    monkeypatch.setenv("METROCRM_ENABLE_MOCK_TELEPHONY", "1")
    response = _client().post(
        "/api/telephony/mock-call",
        json={"executive_id": "exec-1", "client_phone": "abc123", "lead_name": "Test Lead"},
    )
    assert response.status_code == 422
