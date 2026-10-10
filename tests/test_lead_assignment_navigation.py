from pathlib import Path


def test_lead_assignment_suggestions_navigation_is_role_scoped():
    root = Path(__file__).resolve().parents[1]
    base = (root / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'href="/admin/lead-assignment-suggestions"' in base
    assert "role in ['SUPER_ADMIN', 'ADMIN', 'TL']" in base
