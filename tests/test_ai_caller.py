import json

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
