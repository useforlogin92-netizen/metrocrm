from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_template_has_visible_session_countdown():
    html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'id="session-countdown"' in html
    assert "Session expires in" in html
    assert "IDLE_LIMIT_MS = 15 * 60 * 1000" in html
    assert "setInterval(updateCountdown, 1000)" in html
