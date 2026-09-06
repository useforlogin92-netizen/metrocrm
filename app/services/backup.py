"""Secure full CRM backup service with local + optional cloud destinations."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(settings.backup_timezone))
    except Exception:
        return datetime.now()


def _key() -> bytes:
    raw = settings.backup_encryption_key
    if not raw:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY is not configured")
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _encrypted_package(source_zip: Path, destination: Path) -> None:
    nonce = os.urandom(12)
    aes = AESGCM(_key())
    plaintext = source_zip.read_bytes()
    ciphertext = aes.encrypt(nonce, plaintext, None)
    destination.write_bytes(b"MCRMBKP1" + nonce + ciphertext)


def _sqlite_snapshot(database_url: str, target: Path) -> None:
    path = database_url.removeprefix("sqlite:///")
    source = sqlite3.connect(path)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def _database_snapshot(target: Path) -> None:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        _sqlite_snapshot(url, target)
        return
    if url.startswith("postgresql") or url.startswith("postgres"):
        env = os.environ.copy()
        subprocess.run(["pg_dump", url, "-Fc", "-f", str(target)], check=True, env=env)
        return
    raise RuntimeError("Unsupported database URL for backup")


def _add_tree(archive: zipfile.ZipFile, root: Path, arc_prefix: str) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            archive.write(path, f"{arc_prefix}/{path.relative_to(root).as_posix()}")


def _cloud_upload(package: Path, relative_path: str) -> str | None:
    provider = settings.backup_cloud_provider.strip().lower()
    if provider in {"", "none", "disabled"}:
        return None
    if provider in {"s3", "s3_compatible"}:
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=settings.backup_s3_endpoint or None,
            aws_access_key_id=settings.backup_s3_access_key or None,
            aws_secret_access_key=settings.backup_s3_secret_key or None,
            region_name=settings.backup_s3_region or None,
        )
        client.upload_file(str(package), settings.backup_s3_bucket, relative_path)
        return f"s3://{settings.backup_s3_bucket}/{relative_path}"
    raise RuntimeError(f"Unsupported backup cloud provider: {provider}")


def create_full_backup(label: str = "manual") -> dict[str, str | None]:
    """Create one encrypted backup containing DB + uploads, then copy to local/cloud."""
    timestamp = _now()
    date_folder = timestamp.strftime("%Y-%m-%d")
    time_label = "start" if label.lower() == "start" else "end" if label.lower() == "end" else label.lower()
    filename = f"metrocrm_{date_folder}_{time_label}_{timestamp.strftime('%H%M%S')}.mcrmbackup"
    local_root = Path(settings.backup_local_path).expanduser()
    folder = local_root / date_folder
    folder.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="metrocrm-backup-") as temp_dir:
        temp = Path(temp_dir)
        db_snapshot = temp / "database.snapshot"
        _database_snapshot(db_snapshot)
        zip_path = temp / "payload.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_snapshot, "database/database.snapshot")
            _add_tree(archive, Path(settings.uploads_path), "uploads")
            metadata = f"created_at={timestamp.isoformat()}\nlabel={time_label}\ndatabase={settings.database_url.split(':', 1)[0]}\n"
            archive.writestr("backup_metadata.txt", metadata)
        encrypted = folder / filename
        _encrypted_package(zip_path, encrypted)

    cloud_path = f"{date_folder}/{filename}"
    cloud_uri = _cloud_upload(encrypted, cloud_path)
    return {"local_path": str(encrypted), "cloud_path": cloud_uri, "date": date_folder, "label": time_label}


def backup_health() -> dict[str, object]:
    return {
        "local_configured": bool(settings.backup_local_path),
        "cloud_provider": settings.backup_cloud_provider or "none",
        "cloud_configured": bool(settings.backup_cloud_provider and settings.backup_cloud_provider.lower() not in {"none", "disabled"}),
        "timezone": settings.backup_timezone,
        "schedule": ["11:00", "19:00"],
    }
