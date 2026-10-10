from pathlib import Path


def test_caller_workspace_exposes_click_to_call_for_customer():
    template = Path("app/templates/caller_lead_assistant.html").read_text(encoding="utf-8")
    assert 'href="tel:{{ customer.mobile }}"' in template
    assert "Call Customer" in template
