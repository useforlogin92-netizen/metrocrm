from app.config import settings
from app.routers.ai_caller import provider_context, provider_event, provider_tool


class EmptyDB:
    def get(self, model, object_id):
        return None


def test_provider_context_rejects_missing_lead(monkeypatch):
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "provider-secret")
    response = provider_context(999999, "provider-secret", EmptyDB())
    assert response.status_code == 404


def test_provider_tool_rejects_missing_lead(monkeypatch):
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "provider-secret")
    response = provider_tool(999999, {"tool": "update_lead_status", "arguments": {"status": "CLOSED"}}, "provider-secret", EmptyDB())
    assert response.status_code == 404


def test_provider_event_rejects_missing_lead(monkeypatch):
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "provider-secret")
    response = provider_event(999999, {"event": "completed"}, "provider-secret", EmptyDB())
    assert response.status_code == 404
