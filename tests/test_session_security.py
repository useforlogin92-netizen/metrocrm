from pathlib import Path

from app.config import settings


ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_session_max_age_is_15_minutes():
    assert settings.session_max_age == 15 * 60


def test_authenticated_template_disables_cache_and_bfcache():
    html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'http-equiv="Cache-Control"' in html
    assert "no-store" in html
    assert "event.persisted" in html
    assert "window.location.reload()" in html


def test_authenticated_template_has_15_minute_idle_logout():
    html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "15 * 60 * 1000" in html
    assert "window.location.replace('/auth/logout')" in html
