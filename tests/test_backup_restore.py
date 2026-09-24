import hashlib
import io
import sqlite3
import zipfile
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


def test_safe_extract_rejects_duplicate_members(tmp_path):
    from app.services.backup_restore import _safe_extract

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("database/database.snapshot", b"one")
        # Build a deliberately malformed duplicate-member archive without
        # triggering zipfile's own duplicate-name warning.
        archive.NameToInfo.pop("database/database.snapshot", None)
        archive.writestr("database/database.snapshot", b"two")
    payload.seek(0)
    with zipfile.ZipFile(payload) as archive:
        with pytest.raises(RuntimeError, match="Duplicate"):
            _safe_extract(archive, tmp_path / "extract")


def test_safe_extract_rejects_member_count_limit(monkeypatch, tmp_path):
    from app.services import backup_restore

    monkeypatch.setattr(backup_restore, "_MAX_ARCHIVE_MEMBERS", 1)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("database/database.snapshot", b"one")
        archive.writestr("uploads/file.txt", b"two")
    payload.seek(0)
    with zipfile.ZipFile(payload) as archive:
        with pytest.raises(RuntimeError, match="too many members"):
            _safe_extract(archive, tmp_path / "extract")


def test_safe_extract_rejects_total_size_limit(monkeypatch, tmp_path):
    from app.services import backup_restore

    monkeypatch.setattr(backup_restore, "_MAX_TOTAL_UNCOMPRESSED_BYTES", 3)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("database/database.snapshot", b"1234")
    payload.seek(0)
    with zipfile.ZipFile(payload) as archive:
        with pytest.raises(RuntimeError, match="too large"):
            backup_restore._safe_extract(archive, tmp_path / "extract")
