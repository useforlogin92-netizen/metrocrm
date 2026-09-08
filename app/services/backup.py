"""Secure full CRM backup service with local + optional cloud destinations."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings
from app.services.backup_destinations import configured_cloud_providers, copy_to_external_drive, upload_cloud


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


def create_full_backup(label: str = "manual") -> dict[str, object]:
    """Create one encrypted backup and fan it out to every configured destination.

    A destination failure is recorded as a partial failure instead of destroying the
    local master backup. This allows other destinations to remain usable.
    """
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
            metadata = (
                f"created_at={timestamp.isoformat()}\n"
                f"label={time_label}\n"
                f"database={settings.database_url.split(':', 1)[0]}\n"
            )
            archive.writestr("backup_metadata.txt", metadata)
        encrypted = folder / filename
        _encrypted_package(zip_path, encrypted)

    relative_path = f"{date_folder}/{filename}"
    destinations: dict[str, dict[str, str | None]] = {
        "local": {"status": "success", "path": str(encrypted), "error": None}
    }

    if settings.backup_external_path.strip():
        try:
            destinations["external"] = {"status": "success", "path": copy_to_external_drive(encrypted, relative_path), "error": None}
        except Exception as exc:
            destinations["external"] = {"status": "failed", "path": None, "error": str(exc)[:1000]}

    for provider in configured_cloud_providers():
        try:
            uri = upload_cloud(encrypted, relative_path, provider)
            destinations[provider] = {"status": "success", "path": uri, "error": None}
        except Exception as exc:
            destinations[provider] = {"status": "failed", "path": None, "error": str(exc)[:1000]}

    failures = [name for name, item in destinations.items() if item["status"] != "success"]
    return {
        "local_path": str(encrypted),
        "date": date_folder,
        "label": time_label,
        "destinations": destinations,
        "status": "partial_failure" if failures else "success",
        "failed_destinations": failures,
    }


def backup_health() -> dict[str, object]:
    providers = configured_cloud_providers()
    return {
        "local_configured": bool(settings.backup_local_path),
        "external_configured": bool(settings.backup_external_path.strip()),
        "cloud_provider": ",".join(providers) if providers else "none",
        "cloud_providers": providers,
        "cloud_configured": bool(providers),
        "google_drive_configured": bool(settings.backup_google_client_id and settings.backup_google_client_secret and settings.backup_google_refresh_token and settings.backup_google_folder_id),
        "onedrive_configured": bool(settings.backup_onedrive_client_id and settings.backup_onedrive_client_secret and settings.backup_onedrive_refresh_token),
        "timezone": settings.backup_timezone,
        "schedule": ["11:00", "19:00"],
    }
