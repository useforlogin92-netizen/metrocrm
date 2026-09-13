from pathlib import Path

import pytest

from app.config import settings
from app.services.backup import create_full_backup
from app.services.backup_destinations import configured_cloud_providers, copy_to_external_drive


def test_configured_cloud_providers_support_multiple_destinations(monkeypatch):
    monkeypatch.setattr(settings, "backup_cloud_providers", "google_drive, onedrive")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    assert configured_cloud_providers() == ["google_drive", "onedrive"]


def test_backup_fans_out_to_external_destination(tmp_path, monkeypatch):
    database = tmp_path / "metrocrm.db"
    database.write_bytes(b"sqlite-placeholder")
    local_root = tmp_path / "local"
    external_root = tmp_path / "external"
    external_root.mkdir()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database}")
    monkeypatch.setattr(settings, "backup_local_path", str(local_root))
    monkeypatch.setattr(settings, "backup_external_path", str(external_root))
    monkeypatch.setattr(settings, "backup_agent_token", "")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "uploads_path", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "backup_encryption_key", "test-encryption-key")

    monkeypatch.setattr("app.services.backup._database_snapshot", lambda target: Path(target).write_bytes(b"db"))
    result = create_full_backup("test")

    assert result["status"] == "success"
    assert result["destinations"]["local"]["status"] == "success"
    assert result["destinations"]["external"]["status"] == "success"
    external_path = Path(result["destinations"]["external"]["path"])
    assert external_path.exists()
    assert external_path.read_bytes().startswith(b"MCRMBKP1")


def test_external_destination_does_not_create_a_missing_device_mount(tmp_path, monkeypatch):
    package = tmp_path / "backup.mcrmbackup"
    package.write_bytes(b"backup")
    missing = tmp_path / "mnt" / "not-connected-drive"
    monkeypatch.setattr(settings, "backup_external_path", str(missing))

    with pytest.raises(RuntimeError, match="External backup device/path not found"):
        copy_to_external_drive(package, "2026-09-14/backup.mcrmbackup")

    assert not missing.exists()
