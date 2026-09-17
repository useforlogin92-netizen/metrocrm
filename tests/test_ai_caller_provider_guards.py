from app.config import settings
from app.routers.ai_caller import _provider_token, provider_context, provider_event, provider_tool


class EmptyDB:
    def get(self, model, object_id):
        return None


def test_provider_context_rejects_missing_lead(monkeypatch):
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "provider-secret")
    token = _provider_token(999999, now=1000)
    response = provider_context(999999, token, EmptyDB())
    assert response.status_code == 404


def test_provider_tool_rejects_missing_lead(monkeypatch):
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "provider-secret")
    token = _provider_token(999999, now=1000)
    response = provider_tool(999999, {"tool": "update_lead_status", "arguments": {"status": "CLOSED"}}, token, EmptyDB())
    assert response.status_code == 404


def test_provider_event_rejects_missing_lead(monkeypatch):
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "provider-secret")
    token = _provider_token(999999, now=1000)
    response = provider_event(999999, {"event": "completed"}, token, EmptyDB())
    assert response.status_code == 404
