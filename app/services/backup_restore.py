"""Restore encrypted MetroCRM backup packages with integrity and path-safety checks."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_MAGIC = b"MCRMBKP1"
_MAX_ARCHIVE_MEMBERS = 100_000
_MAX_TOTAL_UNCOMPRESSED_BYTES = 10 * 1024 * 1024 * 1024


def _key() -> bytes:
    raw = settings.backup_encryption_key.strip() or settings.secret_key.strip()
    if not raw or raw == "CHANGE-ME-IN-ENV":
        raise RuntimeError("A secure BACKUP_ENCRYPTION_KEY or SECRET_KEY must be configured")
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _decrypt_package(package: Path, target_zip: Path) -> None:
    payload = package.read_bytes()
    if len(payload) <= len(_MAGIC) + 12 or not payload.startswith(_MAGIC):
        raise RuntimeError("Invalid MetroCRM backup package")
    nonce_start = len(_MAGIC)
    nonce = payload[nonce_start:nonce_start + 12]
    ciphertext = payload[nonce_start + 12:]
    plaintext = AESGCM(_key()).decrypt(nonce, ciphertext, None)
    target_zip.write_bytes(plaintext)


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    members = archive.infolist()
    if len(members) > _MAX_ARCHIVE_MEMBERS:
        raise RuntimeError("Backup archive contains too many members")
    total_size = 0
    seen: set[str] = set()
    for member in members:
        name = member.filename
        if not name or name.startswith("/") or "\\" in name:
            raise RuntimeError("Unsafe backup archive member")
        target = (root / name).resolve()
        if root != target and root not in target.parents:
            raise RuntimeError("Unsafe backup archive member")
        normalized = target.relative_to(root).as_posix()
        if normalized in seen:
            raise RuntimeError("Duplicate backup archive member")
        seen.add(normalized)
        if member.file_size < 0 or total_size + member.file_size > _MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise RuntimeError("Backup archive is too large")
        total_size += member.file_size
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)


def _postgres_cli_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "+" in scheme:
        scheme = scheme.split("+", 1)[0]
    return f"{scheme}://{rest}"


def _sqlite_restore(snapshot: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(snapshot)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()


def _postgres_restore(snapshot: Path, database_url: str) -> None:
    subprocess.run(["pg_restore", "--clean", "--if-exists", "-d", _postgres_cli_url(database_url), str(snapshot)], check=True, env=os.environ.copy())


def restore_backup(
    backup_path: str | Path,
    target_database_url: str | None = None,
    target_uploads_path: str | Path | None = None,
    target_application_path: str | Path | None = None,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Restore DB, uploads and optionally the complete application tree."""
    package = Path(backup_path).expanduser().resolve()
    if not package.is_file() or package.suffix != ".mcrmbackup":
        raise FileNotFoundError("Backup package not found")
    if expected_sha256:
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        if digest.lower() != expected_sha256.lower():
            raise RuntimeError("Backup SHA-256 integrity check failed")

    database_url = target_database_url or settings.database_url
    with tempfile.TemporaryDirectory(prefix="metrocrm-restore-") as temp_dir:
        temp = Path(temp_dir)
        zip_path = temp / "payload.zip"
        _decrypt_package(package, zip_path)
        extract_root = temp / "payload"
        extract_root.mkdir()
        with zipfile.ZipFile(zip_path, "r") as archive:
            if "database/database.snapshot" not in archive.namelist():
                raise RuntimeError("Backup does not contain a database snapshot")
            _safe_extract(archive, extract_root)

        snapshot = extract_root / "database" / "database.snapshot"
        if database_url.startswith("sqlite:///"):
            target = Path(database_url.removeprefix("sqlite:///"))
            _sqlite_restore(snapshot, target)
        elif database_url.startswith("postgresql") or database_url.startswith("postgres"):
            _postgres_restore(snapshot, database_url)
        else:
            raise RuntimeError("Unsupported database URL for restore")

        uploads_restored = False
        if target_uploads_path:
            source_uploads = extract_root / "uploads"
            if source_uploads.exists():
                destination = Path(target_uploads_path).expanduser()
                destination.mkdir(parents=True, exist_ok=True)
                for source in source_uploads.rglob("*"):
                    relative = source.relative_to(source_uploads)
                    target = destination / relative
                    if source.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                uploads_restored = True

        application_restored = False
        if target_application_path:
            source_application = extract_root / "application"
            if source_application.exists():
                destination = Path(target_application_path).expanduser()
                destination.mkdir(parents=True, exist_ok=True)
                for source in source_application.rglob("*"):
                    relative = source.relative_to(source_application)
                    target = destination / relative
                    if source.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                application_restored = True

    return {"status": "success", "backup": str(package), "database": database_url.split(":", 1)[0], "uploads_restored": uploads_restored, "application_restored": application_restored}
