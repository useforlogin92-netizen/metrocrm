"""MetroCRM fixed-PC backup agent.

Pulls encrypted backups from the CRM server, stores them on the PC and mirrors
them to an external HDD when connected. It is safe to start at Windows boot;
it immediately catches up and then retries every configured interval.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class AgentError(RuntimeError):
    """Raised when the backup agent receives an unsafe local target."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AgentError(f"{name} is required")
    return value


def _request(url: str, token: str, method: str = "GET") -> bytes:
    request = urllib.request.Request(url, headers={"X-Backup-Agent-Token": token}, method=method)
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_target(root: Path, relative: str) -> Path:
    """Resolve a manifest path while preventing traversal outside *root*."""
    root = root.expanduser().resolve()
    target = (root / relative.replace("/", os.sep)).resolve()
    if target == root or root not in target.parents:
        raise AgentError(f"unsafe backup path: {relative}")
    return target


def _download(base: str, token: str, relative: str, target: Path, expected_size: int, expected_hash: str) -> None:
    url = f"{base}/admin/backups/agent/file/{urllib.parse.quote(relative, safe='/')}"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"X-Backup-Agent-Token": token}), timeout=300) as response:
            with tempfile.NamedTemporaryFile(prefix="metrocrm-", suffix=".part", dir=target.parent, delete=False) as tmp:
                temp_path = Path(tmp.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
        if temp_path.stat().st_size != expected_size or _sha256(temp_path) != expected_hash:
            raise AgentError(f"integrity check failed: {relative}")
        temp_path.replace(target)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def _ack(base: str, token: str, relative: str) -> None:
    query = urllib.parse.urlencode({"relative_path": relative})
    _request(f"{base}/admin/backups/agent/ack?{query}", token, method="POST")


def sync_once() -> dict[str, int]:
    base = _required("METROCRM_URL").rstrip("/")
    token = _required("METROCRM_BACKUP_AGENT_TOKEN")
    local_root = Path(_required("METROCRM_LOCAL_PATH")).expanduser().resolve()
    external_value = os.environ.get("METROCRM_EXTERNAL_PATH", "").strip()
    external_root = Path(external_value).expanduser().resolve() if external_value else None
    local_root.mkdir(parents=True, exist_ok=True)

    manifest = __import__("json").loads(_request(f"{base}/admin/backups/agent/manifest", token).decode("utf-8"))
    downloaded = 0
    skipped = 0
    external_copied = 0
    failed = 0

    for item in manifest.get("files", []):
        relative = str(item["path"])
        expected_size = int(item["size"])
        expected_hash = str(item["sha256"])
        try:
            local_file = _safe_target(local_root, relative)
            if not local_file.is_file() or local_file.stat().st_size != expected_size or _sha256(local_file) != expected_hash:
                _download(base, token, relative, local_file, expected_size, expected_hash)
                downloaded += 1
            else:
                skipped += 1
            _ack(base, token, relative)

            if external_root and external_root.exists():
                external_file = _safe_target(external_root, relative)
                external_file.parent.mkdir(parents=True, exist_ok=True)
                if not external_file.is_file() or external_file.stat().st_size != expected_size or _sha256(external_file) != expected_hash:
                    temp = external_file.with_suffix(external_file.suffix + ".part")
                    temp.parent.mkdir(parents=True, exist_ok=True)
                    with local_file.open("rb") as source, temp.open("wb") as target:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            target.write(chunk)
                    if temp.stat().st_size != expected_size or _sha256(temp) != expected_hash:
                        raise AgentError(f"external HDD integrity check failed: {relative}")
                    temp.replace(external_file)
                    external_copied += 1
        except (OSError, urllib.error.URLError, AgentError, RuntimeError, ValueError, KeyError):
            failed += 1

    return {"downloaded": downloaded, "skipped": skipped, "external_copied": external_copied, "failed": failed}


def main() -> None:
    interval = max(60, int(os.environ.get("METROCRM_POLL_MINUTES", "10"))) * 60
    while True:
        try:
            print(f"MetroCRM backup sync: {sync_once()}", flush=True)
        except Exception as exc:
            print(f"MetroCRM backup sync failed: {exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
