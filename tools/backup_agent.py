"""MetroCRM desktop backup agent.

Polls the server manifest, downloads missing encrypted backups to a fixed local
folder, verifies size/SHA-256, and acknowledges only verified copies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def _request_json(url: str, token: str) -> dict:
    request = Request(url, headers={"X-Backup-Agent-Token": token, "Accept": "application/json"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, token: str, target: Path) -> None:
    request = Request(url, headers={"X-Backup-Agent-Token": token})
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    with urlopen(request, timeout=300) as response, temp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    temp.replace(target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sync_once(server: str, token: str, destination: Path) -> int:
    base = server.rstrip("/")
    manifest = _request_json(f"{base}/admin/backups/agent/manifest", token)
    synced = 0
    for item in manifest.get("files", []):
        relative = str(item.get("path", ""))
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            continue
        target = destination / Path(relative)
        expected_size = int(item["size"])
        expected_hash = str(item["sha256"])
        if target.is_file() and target.stat().st_size == expected_size and _sha256(target) == expected_hash:
            verified = True
        else:
            _download(f"{base}/admin/backups/agent/file/{quote(relative, safe='/')}", token, target)
            verified = target.is_file() and target.stat().st_size == expected_size and _sha256(target) == expected_hash
        if not verified:
            target.unlink(missing_ok=True)
            continue
        ack_url = f"{base}/admin/backups/agent/ack?relative_path={quote(relative, safe='/')}"
        _request_json(ack_url, token)
        synced += 1
    return synced


def main() -> int:
    parser = argparse.ArgumentParser(description="MetroCRM desktop backup agent")
    parser.add_argument("--server", required=True, help="MetroCRM base URL")
    parser.add_argument("--token", required=True, help="Backup agent token")
    parser.add_argument("--destination", required=True, help="Fixed local backup directory")
    parser.add_argument("--interval", type=int, default=600, help="Polling interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run one sync and exit")
    args = parser.parse_args()
    if args.interval < 60:
        parser.error("--interval must be at least 60 seconds")
    destination = Path(args.destination).expanduser().resolve()
    while True:
        sync_once(args.server, args.token, destination)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
