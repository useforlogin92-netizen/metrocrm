"""Secure full CRM backup service with durable destination retry state."""
from __future__ import annotations

import hashlib
import json
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
    raw = settings.backup_encryption_key.strip() or settings.secret_key.strip()
    if not raw or raw == "CHANGE-ME-IN-ENV":
        raise RuntimeError("A secure BACKUP_ENCRYPTION_KEY or SECRET_KEY must be configured")
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _encrypted_package(source_zip: Path, destination: Path) -> None:
    nonce = os.urandom(12)
    aes = AESGCM(_key())
    plaintext = source_zip.read_bytes()
    ciphertext = aes.encrypt(nonce, plaintext, None)
    destination.write_bytes(b"MCRMBKP1" + nonce + ciphertext)


def _decrypt_package(source: Path) -> bytes:
    raw = source.read_bytes()
    if len(raw) <= 8 + 12 or raw[:8] != b"MCRMBKP1":
        raise ValueError("invalid_backup_format")
    return AESGCM(_key()).decrypt(raw[8:20], raw[20:], None)


def _validate_payload(payload: bytes) -> list[str]:
    with zipfile.ZipFile(tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")) as _:
        pass
    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
        tmp.write(payload)
        tmp.flush()
        with zipfile.ZipFile(tmp.name) as archive:
            names = archive.namelist()
            required = {"database/database.snapshot", "backup_metadata.txt"}
            if not required.issubset(names):
                raise ValueError("backup_payload_incomplete")
            bad = archive.testzip()
            if bad:
                raise ValueError(f"backup_payload_corrupt:{bad}")
            return names


def inspect_backup(relative_path: str) -> dict[str, object]:
    """Decrypt and integrity-check an encrypted backup without altering live data."""
    root = Path(settings.backup_local_path).expanduser().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or target.suffix != ".mcrmbackup" or not target.is_file():
        raise ValueError("invalid_backup_path")
    payload = _decrypt_package(target)
    names = _validate_payload(payload)
    return {"relative_path": relative_path, "valid": True, "files": names, "size": target.stat().st_size}


def extract_backup(relative_path: str, destination: Path) -> dict[str, object]:
    """Decrypt and extract a validated backup to a caller-selected staging directory."""
    root = Path(settings.backup_local_path).expanduser().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or target.suffix != ".mcrmbackup" or not target.is_file():
        raise ValueError("invalid_backup_path")
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    payload = _decrypt_package(target)
    _validate_payload(payload)
    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
        tmp.write(payload)
        tmp.flush()
        with zipfile.ZipFile(tmp.name) as archive:
            archive.extractall(destination)
    return {"relative_path": relative_path, "valid": True, "extracted_to": str(destination)}


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
        subprocess.run(["pg_dump", url, "-Fc", "-f", str(target)], check=True, env=os.environ.copy())
        return
    raise RuntimeError("Unsupported database URL for backup")


def _add_tree(archive: zipfile.ZipFile, root: Path, arc_prefix: str) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            archive.write(path, f"{arc_prefix}/{path.relative_to(root).as_posix()}")


def _state_root() -> Path:
    root = Path(settings.backup_local_path).expanduser() / ".queue"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path(relative_path: str) -> Path:
    safe = relative_path.replace("/", "__").replace("\\", "__")
    return _state_root() / f"{safe}.json"


def _write_state(relative_path: str, state: dict[str, object]) -> None:
    target = _state_path(relative_path)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(target)


def _read_state(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _destination_names() -> list[str]:
    names = ["local"]
    if settings.backup_agent_token.strip():
        names.append("agent_pc")
    if settings.backup_external_path.strip():
        names.append("external")
    names.extend(configured_cloud_providers())
    return names


def _retry_destinations(encrypted: Path, relative_path: str, state: dict[str, object]) -> dict[str, object]:
    destinations = state.setdefault("destinations", {})
    assert isinstance(destinations, dict)
    destinations.setdefault("local", {"status": "success", "path": str(encrypted), "error": None})
    if settings.backup_agent_token.strip():
        destinations.setdefault("agent_pc", {"status": "pending", "path": None, "error": None})
    else:
        destinations.pop("agent_pc", None)
    if settings.backup_external_path.strip():
        destinations.setdefault("external", {"status": "pending", "path": None, "error": None})
    for provider in configured_cloud_providers():
        destinations.setdefault(provider, {"status": "pending", "path": None, "error": None})

    if settings.backup_external_path.strip() and destinations["external"]["status"] != "success":
        try:
            destinations["external"] = {"status": "success", "path": copy_to_external_drive(encrypted, relative_path), "error": None}
        except Exception as exc:
            destinations["external"] = {"status": "failed", "path": None, "error": str(exc)[:1000]}

    for provider in configured_cloud_providers():
        if destinations[provider]["status"] == "success":
            continue
        try:
            uri = upload_cloud(encrypted, relative_path, provider)
            destinations[provider] = {"status": "success", "path": uri, "error": None}
        except Exception as exc:
            destinations[provider] = {"status": "failed", "path": None, "error": str(exc)[:1000]}

    required = [name for name in _destination_names() if name != "agent_pc"]
    failures = [name for name in required if destinations[name]["status"] != "success"]
    agent_pending = "agent_pc" in destinations and destinations["agent_pc"]["status"] != "success"
    state["status"] = "partial_failure" if failures or agent_pending else "success"
    state["failed_destinations"] = failures
    state["updated_at"] = _now().isoformat()
    return state


def create_full_backup(label: str = "manual") -> dict[str, object]:
    """Create one encrypted master snapshot, then fan it out and persist retries."""
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
            archive.writestr("backup_metadata.txt", f"created_at={timestamp.isoformat()}\nlabel={time_label}\ndatabase={settings.database_url.split(':', 1)[0]}\n")
        encrypted = folder / filename
        _encrypted_package(zip_path, encrypted)
    relative_path = f"{date_folder}/{filename}"
    state: dict[str, object] = {"relative_path": relative_path, "created_at": timestamp.isoformat(), "label": time_label, "filename": filename, "destinations": {"local": {"status": "success", "path": str(encrypted), "error": None}}}
    state = _retry_destinations(encrypted, relative_path, state)
    _write_state(relative_path, state)
    destinations = state["destinations"]
    assert isinstance(destinations, dict)
    cloud_path = next((item["path"] for name, item in destinations.items() if name not in {"local", "agent_pc", "external"} and item["status"] == "success"), None)
    return {"local_path": str(encrypted), "cloud_path": cloud_path, "date": date_folder, "label": time_label, "destinations": destinations, "status": state["status"], "failed_destinations": state["failed_destinations"]}


def retry_pending_backups() -> list[dict[str, object]]:
    """Retry every queued destination for existing encrypted backups."""
    root = Path(settings.backup_local_path).expanduser()
    results: list[dict[str, object]] = []
    if not root.exists():
        return results
    for state_file in sorted(_state_root().glob("*.json")):
        state = _read_state(state_file)
        if not state:
            continue
        relative_path = str(state.get("relative_path", ""))
        target = (root / relative_path).resolve()
        if root.resolve() not in target.parents or not target.is_file() or target.suffix != ".mcrmbackup":
            continue
        updated = _retry_destinations(target, relative_path, state)
        _write_state(relative_path, updated)
        results.append(updated)
    return results


def acknowledge_agent_backup(relative_path: str) -> bool:
    """Mark a backup as delivered to the fixed desktop backup agent."""
    if not settings.backup_agent_token.strip():
        return False
    root = Path(settings.backup_local_path).expanduser().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or target.suffix != ".mcrmbackup" or not target.is_file():
        return False
    state = _read_state(_state_path(relative_path))
    if not state:
        return False
    destinations = state.setdefault("destinations", {})
    assert isinstance(destinations, dict)
    destinations["agent_pc"] = {"status": "success", "path": relative_path, "error": None}
    required = [name for name in _destination_names() if name != "agent_pc"]
    state["failed_destinations"] = [name for name in required if destinations[name]["status"] != "success"]
    state["status"] = "success" if not state["failed_destinations"] else "partial_failure"
    state["updated_at"] = _now().isoformat()
    _write_state(relative_path, state)
    return True


def backup_health() -> dict[str, object]:
    providers = configured_cloud_providers()
    queue_root = Path(settings.backup_local_path).expanduser() / ".queue"
    queued = 0
    if queue_root.exists():
        queued = sum(1 for p in queue_root.glob("*.json") if (_read_state(p) or {}).get("status") != "success")
    return {"local_configured": bool(settings.backup_local_path), "external_configured": bool(settings.backup_external_path.strip()), "backup_agent_configured": bool(settings.backup_agent_token.strip()), "cloud_provider": ",".join(providers) if providers else "none", "cloud_providers": providers, "cloud_configured": bool(providers), "google_drive_configured": bool(settings.backup_google_client_id and settings.backup_google_client_secret and settings.backup_google_refresh_token and settings.backup_google_folder_id), "onedrive_configured": bool(settings.backup_onedrive_client_id and settings.backup_onedrive_client_secret and settings.backup_onedrive_refresh_token), "queued_retries": queued, "timezone": settings.backup_timezone, "schedule": ["11:00", "19:00"]}
