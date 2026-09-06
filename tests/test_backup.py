from pathlib import Path
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def test_backup_schedule_and_dual_destination_defaults(monkeypatch):
    from app.config import settings
    from app.services.backup import create_full_backup

    root = Path("/tmp/metrocrm-backup-test")
    root.mkdir(parents=True, exist_ok=True)
    db = root / "metrocrm.db"
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("create table if not exists test_data (id integer primary key, value text)")
    conn.execute("insert into test_data(value) values ('ok')")
    conn.commit(); conn.close()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(settings, "backup_local_path", str(root / "backups"))
    monkeypatch.setattr(settings, "uploads_path", str(root / "uploads"))
    monkeypatch.setattr(settings, "backup_encryption_key", "unit-test-secret")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    result = create_full_backup("start")

    path = Path(result["local_path"])
    assert path.exists()
    assert path.parent.name == result["date"]
    assert "_start_" in path.name
    assert path.suffix == ".mcrmbackup"
    assert result["cloud_path"] is None

    raw = path.read_bytes()
    assert raw.startswith(b"MCRMBKP1")
    nonce, ciphertext = raw[8:20], raw[20:]
    plaintext = AESGCM(__import__('hashlib').sha256(b"unit-test-secret").digest()).decrypt(nonce, ciphertext, None)
    payload = root / "payload.zip"
    payload.write_bytes(plaintext)
    with zipfile.ZipFile(payload) as archive:
        assert "database/database.snapshot" in archive.namelist()
        assert "backup_metadata.txt" in archive.namelist()
