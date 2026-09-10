from pathlib import Path


def test_dashboard_uses_simple_language_label_with_language_icon():
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    assert "labelText.textContent='🌐 Language'" in template
    assert "Choose caller speech language" in template
    assert "Caller Language" not in template
