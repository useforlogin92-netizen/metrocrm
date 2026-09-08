"""MetroCRM desktop backup agent.

Syncs encrypted server backups to a local/external drive without storing database
credentials. Configure with environment variables:
  METROCRM_URL=https://metrocrm-live.onrender.com
  METROCRM_BACKUP_AGENT_TOKEN=<same secret as server BACKUP_AGENT_TOKEN>
  METROCRM_EXTERNAL_PATH=D:\\MetroCRM_Backups
  METROCRM_POLL_MINUTES=60

The agent is intentionally standard-library-only so it can run on a Windows PC.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _request(url: str, token: str) -> bytes:
    request = urllib.request.Request(url, headers={"X-Backup-Agent-Token": token}, method="GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def sync_once() -> dict[str, int]:
    base = _required("METROCRM_URL").rstrip("/")
    token = _required("METROCRM_BACKUP_AGENT_TOKEN")
    destination = Path(_required("METROCRM_EXTERNAL_PATH")).expanduser()
    destination.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(_request(f"{base}/admin/backups/agent/manifest", token).decode("utf-8"))
    downloaded = 0
    skipped = 0
    failed = 0

    for item in manifest.get("files", []):
        relative = str(item["path"]).replace("/", os.sep)
        target = (destination / relative).resolve()
        root = destination.resolve()
        if root not in target.parents:
            failed += 1
            continue
        expected_size = int(item["size"])
        if target.is_file() and target.stat().st_size == expected_size:
            skipped += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        url_path = str(item["path"])
        url = f"{base}/admin/backups/agent/file/{url_path}"
        try:
            payload = _request(url, token)
            if len(payload) != expected_size:
                raise RuntimeError("download size does not match server manifest")
            with tempfile.NamedTemporaryFile(prefix="metrocrm-", suffix=".part", dir=target.parent, delete=False) as tmp:
                temp_path = Path(tmp.name)
                tmp.write(payload)
                tmp.flush()
            temp_path.replace(target)
            downloaded += 1
        except (OSError, urllib.error.URLError, RuntimeError):
            failed += 1
            try:
                temp_path.unlink(missing_ok=True)
            except UnboundLocalError:
                pass

    return {"downloaded": downloaded, "skipped": skipped, "failed": failed}


def main() -> None:
    interval = max(5, int(os.environ.get("METROCRM_POLL_MINUTES", "60"))) * 60
    while True:
        try:
            result = sync_once()
            print(f"MetroCRM backup sync: {result}", flush=True)
        except Exception as exc:
            print(f"MetroCRM backup sync failed: {exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
