from pathlib import Path
import hashlib
import sqlite3
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def test_backup_schedule_and_dual_destination_defaults(monkeypatch):
    from app.config import settings
    from app.services.backup import create_full_backup

    root = Path("/tmp/metrocrm-backup-test")
    root.mkdir(parents=True, exist_ok=True)
    db = root / "metrocrm.db"
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
    plaintext = AESGCM(hashlib.sha256(b"unit-test-secret").digest()).decrypt(nonce, ciphertext, None)
    payload = root / "payload.zip"
    payload.write_bytes(plaintext)
    with zipfile.ZipFile(payload) as archive:
        assert "database/database.snapshot" in archive.namelist()
        assert "backup_metadata.txt" in archive.namelist()


def test_backup_uses_application_secret_when_dedicated_key_is_missing(monkeypatch):
    from app.config import settings
    from app.services.backup import _key

    monkeypatch.setattr(settings, "backup_encryption_key", "")
    monkeypatch.setattr(settings, "secret_key", "production-secret")
    assert _key() == hashlib.sha256(b"production-secret").digest()


def test_restore_uses_application_secret_when_dedicated_key_is_missing(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.backup import create_full_backup
    from app.services.backup_restore import restore_backup

    source_db = tmp_path / "source.db"
    conn = sqlite3.connect(source_db)
    conn.execute("create table restore_data (id integer primary key, value text)")
    conn.execute("insert into restore_data(value) values ('restored')")
    conn.commit(); conn.close()

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "proof.txt").write_text("backup-upload", encoding="utf-8")
    backup_root = tmp_path / "backups"

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{source_db}")
    monkeypatch.setattr(settings, "backup_local_path", str(backup_root))
    monkeypatch.setattr(settings, "uploads_path", str(uploads))
    monkeypatch.setattr(settings, "backup_encryption_key", "")
    monkeypatch.setattr(settings, "secret_key", "production-secret")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    result = create_full_backup("restore-test")

    target_db = tmp_path / "restored.db"
    target_uploads = tmp_path / "restored-uploads"
    restored = restore_backup(
        result["local_path"],
        target_database_url=f"sqlite:///{target_db}",
        target_uploads_path=target_uploads,
        expected_sha256=hashlib.sha256(Path(result["local_path"]).read_bytes()).hexdigest(),
    )

    assert restored["status"] == "success"
    assert restored["uploads_restored"] is True
    conn = sqlite3.connect(target_db)
    try:
        row = conn.execute("select value from restore_data where id = 1").fetchone()
        assert row == ("restored",)
    finally:
        conn.close()
    assert (target_uploads / "proof.txt").read_text(encoding="utf-8") == "backup-upload"


def test_backup_rejects_placeholder_secrets(monkeypatch):
    from app.config import settings
    from app.services.backup import _key

    monkeypatch.setattr(settings, "backup_encryption_key", "")
    monkeypatch.setattr(settings, "secret_key", "CHANGE-ME-IN-ENV")
    try:
        _key()
    except RuntimeError as exc:
        assert "secure BACKUP_ENCRYPTION_KEY or SECRET_KEY" in str(exc)
    else:
        raise AssertionError("placeholder secret must not be accepted")


def test_restore_rejects_placeholder_secrets(monkeypatch):
    from app.config import settings
    from app.services.backup_restore import _key

    monkeypatch.setattr(settings, "backup_encryption_key", "")
    monkeypatch.setattr(settings, "secret_key", "CHANGE-ME-IN-ENV")
    try:
        _key()
    except RuntimeError as exc:
        assert "secure BACKUP_ENCRYPTION_KEY or SECRET_KEY" in str(exc)
    else:
        raise AssertionError("placeholder secret must not be accepted")


def test_backup_scheduler_registers_11am_and_7pm(monkeypatch):
    from app.config import settings
    import app.services.backup_scheduler as module

    class FakeScheduler:
        running = False
        def __init__(self, **kwargs):
            self.jobs = []
        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))
        def start(self):
            self.running = True
        def shutdown(self, **kwargs):
            self.running = False

    monkeypatch.setattr(module, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(settings, "backup_enabled", True)
    module._scheduler = None
    module.start_backup_scheduler()
    scheduler = module._scheduler
    assert scheduler is not None
    assert [job[2]["id"] for job in scheduler.jobs] == ["metrocrm_backup_start", "metrocrm_backup_end", "metrocrm_backup_retry"]

    def cron_field(trigger, name):
        return next(field for field in trigger.fields if field.name == name)

    assert [str(cron_field(job[1], "hour")) for job in scheduler.jobs[:2]] == ["11", "19"]
    assert [str(cron_field(job[1], "minute")) for job in scheduler.jobs[:2]] == ["0", "0"]
    assert str(cron_field(scheduler.jobs[2][1], "minute")) == "*/10"
    module.stop_backup_scheduler()
