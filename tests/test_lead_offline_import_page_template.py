from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "app" / "templates"


def test_offline_lead_import_template_exists_and_renders():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("lead_offline_import.html")

    rendered = template.render(
        request=None,
        username="test-admin",
        role="SUPER_ADMIN",
        avatar="T",
        csrf_token="test-csrf-token",
        message="",
        error="",
        show_user_management=True,
        show_integrations=False,
        show_alerts=False,
        show_approvals=True,
    )

    assert "Lead Excel Upload" in rendered
    assert 'name="csrf_token" value="test-csrf-token"' in rendered
    assert 'name="file"' in rendered
    assert "/super-admin/leads/offline-import/template" in rendered
