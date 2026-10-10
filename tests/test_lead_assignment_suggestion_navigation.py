from pathlib import Path


def test_assignment_suggestions_sidebar_link_is_limited_to_authorized_roles():
    template = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert "{% if role in ['SUPER_ADMIN','ADMIN','TL'] %}" in template
    assert 'href="/admin/lead-assignment-suggestions"' in template
    assert "Lead Assignment Suggestions" in template
