import hashlib
import sqlite3
from pathlib import Path

import pytest


def _make_backup(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.backup import create_full_backup

    source = tmp_path / "source.db"
    conn = sqlite3.connect(source)
    conn.execute("create table data (id integer primary key, value text)")
    conn.execute("insert into data(value) values ('restore-test')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{source}")
    monkeypatch.setattr(settings, "backup_local_path", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "uploads_path", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "backup_encryption_key", "restore-test-secret")
    monkeypatch.setattr(settings, "backup_agent_token", "")
    monkeypatch.setattr(settings, "backup_external_path", "")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    return create_full_backup("restore-test")


def test_restore_encrypted_sqlite_backup(monkeypatch, tmp_path):
    result = _make_backup(monkeypatch, tmp_path)
    from app.services.backup_restore import restore_backup

    restored = tmp_path / "restored.db"
    response = restore_backup(result["local_path"], f"sqlite:///{restored}")
    assert response["status"] == "success"

    conn = sqlite3.connect(restored)
    try:
        row = conn.execute("select value from data").fetchone()
    finally:
        conn.close()
    assert row == ("restore-test",)


def test_restore_rejects_bad_sha256(monkeypatch, tmp_path):
    result = _make_backup(monkeypatch, tmp_path)
    from app.services.backup_restore import restore_backup

    with pytest.raises(RuntimeError, match="SHA-256"):
        restore_backup(result["local_path"], f"sqlite:///{tmp_path / 'restored.db'}", expected_sha256="0" * 64)


def test_restore_rejects_invalid_package(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.backup_restore import restore_backup

    monkeypatch.setattr(settings, "backup_encryption_key", "restore-test-secret")
    package = tmp_path / "bad.mcrmbackup"
    package.write_bytes(b"not-a-metrocrm-backup")
    with pytest.raises(RuntimeError, match="Invalid MetroCRM backup"):
        restore_backup(package, f"sqlite:///{tmp_path / 'restored.db'}")
