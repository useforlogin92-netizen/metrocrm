def test_backup_cloud_configuration_routes_exist():
    from app.routers.backups import router

    paths = {getattr(route, "path", None) for route in router.routes}
    assert "/admin/backups/configure" in paths
    assert "/admin/backups/google/connect" in paths
    assert "/admin/backups/google/callback" in paths
    assert "/admin/backups/onedrive/connect" in paths
    assert "/admin/backups/onedrive/callback" in paths


def test_backup_status_template_exposes_configuration_links():
    from pathlib import Path

    content = Path("app/templates/backup_status.html").read_text(encoding="utf-8")
    assert "/admin/backups/configure?provider=google_drive" in content
    assert "/admin/backups/configure?provider=onedrive" in content
