from pathlib import Path
import hashlib
import sqlite3
import zipfile


def test_full_backup_contains_application_manifest(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.backup import create_full_backup

    db = tmp_path / "source.db"
    conn = sqlite3.connect(db)
    conn.execute("create table test_data (id integer primary key, value text)")
    conn.execute("insert into test_data(value) values ('application')")
    conn.commit(); conn.close()

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "file.txt").write_text("upload", encoding="utf-8")
    backup_root = tmp_path / "backups"

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(settings, "backup_local_path", str(backup_root))
    monkeypatch.setattr(settings, "uploads_path", str(uploads))
    monkeypatch.setattr(settings, "backup_encryption_key", "application-secret")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    monkeypatch.setattr(settings, "backup_external_path", "")
    monkeypatch.setattr(settings, "backup_agent_token", "")

    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("print('metrocrm')", encoding="utf-8")
    result = create_full_backup("application")

    raw = Path(result["local_path"]).read_bytes()
    nonce, ciphertext = raw[8:20], raw[20:]
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    plaintext = AESGCM(hashlib.sha256(b"application-secret").digest()).decrypt(nonce, ciphertext, None)
    payload = tmp_path / "payload.zip"
    payload.write_bytes(plaintext)
    with zipfile.ZipFile(payload) as archive:
        assert "application/app.py" in archive.namelist()
        assert "application/manifest.json" in archive.namelist()
        assert "database/database.snapshot" in archive.namelist()
        assert "uploads/file.txt" in archive.namelist()
        assert ".env" not in "\n".join(archive.namelist())


def test_b2_uses_s3_compatible_configuration(monkeypatch, tmp_path):
    from app.config import settings
    import app.services.backup_destinations as destinations

    class FakeClient:
        def __init__(self, package):
            self.package = package
            self.uploaded = None

        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            self.uploaded = (filename, bucket, key, ExtraArgs)

        def head_object(self, Bucket, Key):
            assert Bucket == "metrocrm-test"
            assert Key == "2026-09-14/backup.mcrmbackup"
            return {
                "ContentLength": self.package.stat().st_size,
                "Metadata": {"sha256": hashlib.sha256(self.package.read_bytes()).hexdigest()},
            }

    monkeypatch.setattr(settings, "backup_s3_endpoint", "https://s3.us-west-002.backblazeb2.com")
    monkeypatch.setattr(settings, "backup_s3_bucket", "metrocrm-test")
    monkeypatch.setattr(settings, "backup_s3_access_key", "key")
    monkeypatch.setattr(settings, "backup_s3_secret_key", "secret")
    monkeypatch.setattr(settings, "backup_s3_region", "us-west-002")

    package = tmp_path / "backup.mcrmbackup"
    package.write_bytes(b"backup")
    client = FakeClient(package)

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            assert args == ("s3",)
            assert kwargs["endpoint_url"].startswith("https://s3.")
            assert kwargs["region_name"] == "us-west-002"
            assert "config" in kwargs
            return client

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3)
    uri = destinations.upload_cloud(package, "2026-09-14/backup.mcrmbackup", "s3")
    assert uri == "s3://metrocrm-test/2026-09-14/backup.mcrmbackup"
    assert client.uploaded[1:3] == ("metrocrm-test", "2026-09-14/backup.mcrmbackup")
    assert client.uploaded[3]["Metadata"]["sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
