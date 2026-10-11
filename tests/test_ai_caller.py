import json
from types import SimpleNamespace

import pytest

from app.routers.ai_caller import _lead_in_scope, _provider_claims, _provider_token
from app.services.ai_caller import _validate_tool_arguments, system_prompt, tool_definitions


def test_ai_caller_prompt_has_hallucination_guardrails_and_language_support():
    prompt = system_prompt().lower()
    assert "never invent" in prompt
    assert "crm" in prompt
    assert "hindi" in prompt
    assert "hinglish" in prompt
    assert "legal" in prompt


def test_ai_caller_tools_are_allowlisted_and_have_strict_arguments():
    tools = tool_definitions()
    names = {tool["name"] for tool in tools}
    assert names == {"search_properties", "get_property", "record_call_outcome", "update_lead_status"}
    for tool in tools:
        assert tool["parameters"]["additionalProperties"] is False
    status_tool = next(tool for tool in tools if tool["name"] == "update_lead_status")
    assert status_tool["parameters"]["properties"]["status"]["enum"] == [
        "NEW", "CONTACTED", "INTERESTED", "FOLLOW_UP", "SITE_VISIT", "NOT_INTERESTED", "CLOSED"
    ]


def test_ai_caller_payload_does_not_require_provider_credentials_in_source():
    # Credentials must be deployment environment values, never hard-coded in the project.
    from app.config import settings
    assert isinstance(settings.ai_caller_provider_secret, str)
    assert "api_key" not in json.dumps(tool_definitions()).lower()


def test_ai_caller_provider_token_is_bound_to_one_lead(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "test-secret")
    token = _provider_token(123, now=1_000)
    assert _provider_claims(token, 123, now=1_005)["lead_id"] == 123
    assert _provider_claims(token, 124, now=1_005) is None


def test_ai_caller_provider_token_rejects_static_secret_and_expired_token(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ai_caller_provider_secret", "test-secret")
    assert _provider_claims("test-secret", 123, now=1_005) is None
    token = _provider_token(123, now=1_000)
    assert _provider_claims(token, 123, now=1_600) is None


class _ScopeDB:
    def __init__(self, users):
        self.users = users

    def scalars(self, stmt):
        params = stmt.compile().params
        manager_ids = set()
        for value in params.values():
            if isinstance(value, (list, tuple, set)):
                manager_ids.update(value)
        scoped_users = [user for user in self.users if user.reporting_manager_id in manager_ids]

        class Result:
            def __init__(self, users):
                self._users = users

            def all(self):
                return self._users

        return Result(scoped_users)


def _user(user_id, role, manager_id=None):
    return SimpleNamespace(id=user_id, role=role, reporting_manager_id=manager_id)


def _lead(owner_id):
    return SimpleNamespace(assigned_user_id=owner_id)


def test_ai_caller_scope_allows_assigned_lead():
    user = _user(1, "SALES_EXECUTIVE")
    assert _lead_in_scope(user, _lead(1), _ScopeDB([])) is True


def test_ai_caller_scope_denies_other_sales_lead():
    user = _user(1, "SALES_EXECUTIVE")
    assert _lead_in_scope(user, _lead(2), _ScopeDB([])) is False


def test_ai_caller_scope_allows_manager_reporting_tree():
    user = _user(1, "MANAGER")
    child = _user(2, "SALES_EXECUTIVE", 1)
    grandchild = _user(3, "TELECALLER", 2)
    assert _lead_in_scope(user, _lead(3), _ScopeDB([child, grandchild])) is True


def test_ai_caller_scope_denies_manager_outside_tree():
    user = _user(1, "MANAGER")
    child = _user(2, "SALES_EXECUTIVE", 1)
    outsider = _user(3, "SALES_EXECUTIVE", 99)
    assert _lead_in_scope(user, _lead(3), _ScopeDB([child, outsider])) is False


def test_ai_caller_scope_allows_admin_any_lead():
    for role in ("ADMIN", "SUPER_ADMIN"):
        assert _lead_in_scope(_user(1, role), _lead(999), _ScopeDB([])) is True



def test_ai_caller_tool_arguments_are_validated_server_side():
    _validate_tool_arguments("record_call_outcome", {
        "outcome": "FOLLOW_UP",
        "summary": "Customer asked for a callback",
        "next_action": "Call tomorrow",
    })
    _validate_tool_arguments("update_lead_status", {"status": "CONTACTED"})
    _validate_tool_arguments("search_properties", {
        "location": "Malad",
        "budget_min": 5000000,
        "budget_max": 20000000,
    })


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("update_lead_status", {"status": "ADMIN"}),
        ("record_call_outcome", {"outcome": "HACKED", "summary": "bad"}),
        ("get_property", {"unit_id": True}),
        ("get_property", {"unit_id": 0}),
        ("search_properties", {"budget_min": float("inf")}),
        ("search_properties", {"unexpected": "field"}),
        ("record_call_outcome", {"outcome": "FOLLOW_UP", "summary": "ok", "extra": "field"}),
        ("search_properties", {"budget_min": 200, "budget_max": 100}),
        ("search_properties", {"carpet_area_min": 1000, "carpet_area_max": 100}),
        ("record_call_outcome", {"outcome": "FOLLOW_UP", "summary": 123}),
    ],
)
def test_ai_caller_tool_arguments_reject_invalid_payloads(tool, arguments):
    with pytest.raises(ValueError):
        _validate_tool_arguments(tool, arguments)


def test_ai_caller_tool_arguments_reject_unknown_tools_and_missing_required_fields():
    with pytest.raises(ValueError, match="Tool not allowed"):
        _validate_tool_arguments("delete_everything", {})
    with pytest.raises(ValueError, match="Missing required"):
        _validate_tool_arguments("get_property", {})
