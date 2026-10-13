from pathlib import Path
from types import SimpleNamespace

import pytest

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



def test_sales_executive_can_view_but_not_set_sales_targets(db_session, monkeypatch):
    actor = SimpleNamespace(role="SALES_EXECUTIVE", username="sales-exec-target-view", id=777)
    monkeypatch.setattr(crm_plus, "current_user", lambda request, db: actor)
    monkeypatch.setattr(crm_plus, "csrf_token", lambda request: "test-csrf")

    response = crm_plus.targets_page(_request("/crm/advanced/targets"), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "Sales Targets" in html
    assert "Set monthly targets" not in html
    assert "Save Target" not in html



@pytest.mark.parametrize(
    "page_fn",
    [
        crm_plus.advanced_hub,
        crm_plus.tasks_page,
        crm_plus.targets_page,
        crm_plus.payments_page,
        crm_plus.tickets_page,
        crm_plus.possession_page,
    ],
)
def test_accountant_cannot_open_sales_crm_workspaces(page_fn, db_session, monkeypatch):
    actor = SimpleNamespace(role="ACCOUNTANT", username="accountant", id=778)
    monkeypatch.setattr(crm_plus, "current_user", lambda request, db: actor)

    response = page_fn(_request(), db_session)

    assert response.status_code == 303
    assert response.headers["location"] in {"/", "/dashboard"}


@pytest.mark.parametrize(
    "page_fn",
    [
        crm_plus.advanced_hub,
        crm_plus.tasks_page,
        crm_plus.targets_page,
        crm_plus.payments_page,
        crm_plus.tickets_page,
        crm_plus.possession_page,
    ],
)
def test_sales_executive_can_open_scoped_crm_workspaces(page_fn, db_session, monkeypatch):
    actor = SimpleNamespace(role="SALES_EXECUTIVE", username="sales-exec", id=779)
    monkeypatch.setattr(crm_plus, "current_user", lambda request, db: actor)
    monkeypatch.setattr(crm_plus, "csrf_token", lambda request: "test-csrf")

    response = page_fn(_request(), db_session)

    assert response.status_code == 200



def test_sales_and_caller_dashboard_exposes_core_workflows():
    dashboard = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    base = Path("app/templates/base.html").read_text(encoding="utf-8")
    sales_roles = "['SUPER_ADMIN','ADMIN','MANAGER','TL','SALES_EXECUTIVE','TELECALLER']"
    for label, href in (
        ("My Tasks &amp; Follow-ups", "/crm/advanced/tasks"),
        ("Site Visits", "/site-visits"),
        ("WhatsApp Outreach", "/whatsapp"),
        ("Email Property Details", "/email"),
        ("Advanced CRM Hub", "/crm/advanced"),
    ):
        assert label in dashboard
        assert href in dashboard
    assert sales_roles in base
    assert "My Tasks &amp; Follow-ups" in base
    assert "/crm/advanced/tasks" in base


def test_sales_targets_shortcut_excludes_telecaller():
    dashboard = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    target_link = dashboard.index('href="/crm/advanced/targets"')
    role_gate = "{% if role in ['SUPER_ADMIN','ADMIN','MANAGER','TL','SALES_EXECUTIVE'] %}"
    assert dashboard.rfind(role_gate, 0, target_link) > dashboard.rfind("{% endif %}", 0, target_link)
