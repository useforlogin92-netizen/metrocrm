from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_super_admin_sidebar_uses_only_dedicated_privileged_routes():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "/super-admin/property-submissions" in base
    assert "/super-admin/property-data" in base
    assert "/super-admin/users" in base
    assert "/super-admin/users/pending" in base
    assert "/super-admin/backups/status" in base
    assert "href=\"/admin/property-data\"" not in base
    assert "href=\"/admin/users\"" not in base
    assert "href=\"/admin/users/pending\"" not in base
    assert "href=\"/admin/backups/status\"" not in base


def test_super_admin_dashboard_uses_dedicated_privileged_routes():
    dashboard = (ROOT / "app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert "/super-admin/business-reports" in dashboard
    assert "/super-admin/data-tools" in dashboard
    assert "/super-admin/leads/offline-import" in dashboard
    assert "/super-admin/property-data" in dashboard
    assert "/super-admin/property-data/social" in dashboard
    assert "/super-admin/property-submissions" in dashboard
    assert "/super-admin/users/pending" in dashboard
    assert "/super-admin/backups/status" in dashboard
