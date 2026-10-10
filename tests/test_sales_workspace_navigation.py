from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request

from app.routers import crm_plus


def _request(path="/crm/advanced"):
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b"", "session": {}})


def test_dashboard_caller_actions_are_limited_to_sales_and_management_roles():
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    role_gate = "{% if role in ['SUPER_ADMIN','ADMIN','MANAGER','TL','SALES_EXECUTIVE','TELECALLER'] %}"
    for label in ("Caller Property Search", "Lead Management", "Advanced CRM Hub"):
        position = template.index(label)
        assert template.rfind(role_gate, 0, position) > template.rfind("{% endif %}", 0, position)


def test_sales_executive_advanced_hub_hides_campaign_and_partner_admin_tools(db_session, monkeypatch):
    actor = SimpleNamespace(role="SALES_EXECUTIVE", username="sales-exec", id=123)
    monkeypatch.setattr(crm_plus, "current_user", lambda request, db: actor)
    monkeypatch.setattr(crm_plus, "csrf_token", lambda request: "test-csrf")

    response = crm_plus.advanced_hub(_request(), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "Tasks &amp; Follow-up" in html
    assert "Sales Targets" in html
    assert "Payment Milestones" in html
    assert "Customer Service" in html
    assert "Possession Checklist" in html
    assert "Marketing Campaigns" not in html
    assert "Channel Partners" not in html


def test_telecaller_advanced_hub_shows_followup_tools_without_sales_management_links(db_session, monkeypatch):
    actor = SimpleNamespace(role="TELECALLER", username="telecaller", id=124)
    monkeypatch.setattr(crm_plus, "current_user", lambda request, db: actor)
    monkeypatch.setattr(crm_plus, "csrf_token", lambda request: "test-csrf")

    response = crm_plus.advanced_hub(_request(), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "Tasks &amp; Follow-up" in html
    assert "Sales Targets" not in html
    assert "Payment Milestones" not in html
    assert "Marketing Campaigns" not in html
    assert "Channel Partners" not in html
