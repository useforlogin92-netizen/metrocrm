import json
from types import SimpleNamespace

from app.routers.ai_caller import _lead_in_scope
from app.services.ai_caller import system_prompt, tool_definitions


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


class _ScopeDB:
    def __init__(self, users):
        self.users = users

    def scalars(self, stmt):
        class Result:
            def __init__(self, users):
                self._users = users

            def all(self):
                return self._users

        # Mirror the production query's reporting_manager_id IN (...) predicate so
        # the fixture verifies actual tree filtering rather than returning every user.
        manager_ids = set()
        for value in stmt.compile().params.values():
            if isinstance(value, (list, tuple, set)):
                manager_ids.update(value)
        return Result([user for user in self.users if user.reporting_manager_id in manager_ids])


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
