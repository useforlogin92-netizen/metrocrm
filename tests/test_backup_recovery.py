from pathlib import Path
import hashlib
import sqlite3
import zipfile

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _decrypt_backup(path: Path, secret: str) -> bytes:
    raw = path.read_bytes()
    assert raw.startswith(b"MCRMBKP1")
    nonce, ciphertext = raw[8:20], raw[20:]
    return AESGCM(hashlib.sha256(secret.encode()).digest()).decrypt(nonce, ciphertext, None)


def test_encrypted_backup_round_trip_restores_database_and_metadata(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.backup import create_full_backup

    source_db = tmp_path / "source.db"
    conn = sqlite3.connect(source_db)
    conn.execute("create table customers (id integer primary key, name text not null)")
    conn.execute("insert into customers(name) values ('Recovery Test')")
    conn.commit()
    conn.close()

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "document.txt").write_text("recovery payload", encoding="utf-8")
    backup_root = tmp_path / "backups"
    secret = "recovery-test-secret"

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{source_db}")
    monkeypatch.setattr(settings, "backup_local_path", str(backup_root))
    monkeypatch.setattr(settings, "uploads_path", str(uploads))
    monkeypatch.setattr(settings, "backup_encryption_key", secret)
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    monkeypatch.setattr(settings, "backup_external_path", "")
    monkeypatch.setattr(settings, "backup_agent_token", "")

    result = create_full_backup("recovery")
    backup = Path(result["local_path"])
    plaintext = _decrypt_backup(backup, secret)

    payload = tmp_path / "payload.zip"
    payload.write_bytes(plaintext)
    restore_db = tmp_path / "restored.db"
    restore_uploads = tmp_path / "restored_uploads"
    restore_uploads.mkdir()

    with zipfile.ZipFile(payload) as archive:
        archive.extract("database/database.snapshot", tmp_path / "restore")
        archive.extract("uploads/document.txt", tmp_path / "restore")
        metadata = archive.read("backup_metadata.txt").decode("utf-8")

    restored_snapshot = tmp_path / "restore" / "database" / "database.snapshot"
    restore_db.write_bytes(restored_snapshot.read_bytes())
    restored_file = tmp_path / "restore" / "uploads" / "document.txt"

    conn = sqlite3.connect(restore_db)
    row = conn.execute("select name from customers where id = 1").fetchone()
    conn.close()

    assert row == ("Recovery Test",)
    assert restored_file.read_text(encoding="utf-8") == "recovery payload"
    assert "label=recovery" in metadata
    assert "created_at=" in metadata


def test_tampered_encrypted_backup_is_rejected(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.backup import create_full_backup

    db = tmp_path / "source.db"
    conn = sqlite3.connect(db)
    conn.execute("create table test_data (id integer primary key, value text)")
    conn.execute("insert into test_data(value) values ('safe')")
    conn.commit()
    conn.close()

    secret = "tamper-test-secret"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(settings, "backup_local_path", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "uploads_path", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "backup_encryption_key", secret)
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    monkeypatch.setattr(settings, "backup_external_path", "")
    monkeypatch.setattr(settings, "backup_agent_token", "")

    backup = Path(create_full_backup("tamper")["local_path"])
    raw = bytearray(backup.read_bytes())
    raw[-1] ^= 0x01
    tampered = tmp_path / "tampered.mcrmbackup"
    tampered.write_bytes(raw)

    with pytest.raises(Exception):
        _decrypt_backup(tampered, secret)


def test_external_mirror_is_byte_identical(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.backup import create_full_backup

    db = tmp_path / "source.db"
    conn = sqlite3.connect(db)
    conn.execute("create table test_data (id integer primary key, value text)")
    conn.execute("insert into test_data(value) values ('mirror')")
    conn.commit()
    conn.close()

    backup_root = tmp_path / "backups"
    external_root = tmp_path / "external"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(settings, "backup_local_path", str(backup_root))
    monkeypatch.setattr(settings, "uploads_path", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "backup_encryption_key", "mirror-secret")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    monkeypatch.setattr(settings, "backup_external_path", str(external_root))
    monkeypatch.setattr(settings, "backup_agent_token", "")

    result = create_full_backup("mirror")
    local = Path(result["local_path"])
    mirrored = external_root / result["date"] / local.name

    assert mirrored.is_file()
    assert hashlib.sha256(local.read_bytes()).digest() == hashlib.sha256(mirrored.read_bytes()).digest()
