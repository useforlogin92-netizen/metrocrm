from __future__ import annotations

import hashlib
from pathlib import Path

from tools import metrocrm_backup_agent as agent


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        if size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_sync_once_downloads_verifies_and_mirrors(monkeypatch, tmp_path):
    payload = b"encrypted-backup-payload"
    digest = hashlib.sha256(payload).hexdigest()
    local_root = tmp_path / "pc"
    external_root = tmp_path / "hdd"
    monkeypatch.setenv("METROCRM_URL", "https://crm.example")
    monkeypatch.setenv("METROCRM_BACKUP_AGENT_TOKEN", "secret")
    monkeypatch.setenv("METROCRM_LOCAL_PATH", str(local_root))
    monkeypatch.setenv("METROCRM_EXTERNAL_PATH", str(external_root))

    relative = "2026-09-09/backup.mcrmbackup"
    calls: list[tuple[str, str]] = []

    def fake_request(url, token, method="GET"):
        calls.append((url, method))
        if url.endswith("/manifest"):
            import json
            return json.dumps({"files": [{"path": relative, "size": len(payload), "sha256": digest}]}).encode()
        return b'{"status":"success"}'

    monkeypatch.setattr(agent, "_request", fake_request)
    monkeypatch.setattr(agent.urllib.request, "urlopen", lambda request, timeout=300: _Response(payload))

    result = agent.sync_once()

    assert result == {"downloaded": 1, "skipped": 0, "external_copied": 1, "failed": 0}
    assert (local_root / relative).read_bytes() == payload
    assert (external_root / relative).read_bytes() == payload
    assert any(method == "POST" and "/agent/ack?" in url for url, method in calls)


def test_sync_once_reuses_valid_local_backup(monkeypatch, tmp_path):
    payload = b"already-safe"
    digest = hashlib.sha256(payload).hexdigest()
    local_root = tmp_path / "pc"
    local_root.mkdir()
    relative = "2026-09-09/backup.mcrmbackup"
    target = local_root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    monkeypatch.setenv("METROCRM_URL", "https://crm.example")
    monkeypatch.setenv("METROCRM_BACKUP_AGENT_TOKEN", "secret")
    monkeypatch.setenv("METROCRM_LOCAL_PATH", str(local_root))
    monkeypatch.delenv("METROCRM_EXTERNAL_PATH", raising=False)

    calls = []
    def fake_request(url, token, method="GET"):
        calls.append((url, method))
        if url.endswith("/manifest"):
            import json
            return json.dumps({"files": [{"path": relative, "size": len(payload), "sha256": digest}]}).encode()
        return b'{"status":"success"}'

    monkeypatch.setattr(agent, "_request", fake_request)
    result = agent.sync_once()

    assert result == {"downloaded": 0, "skipped": 1, "external_copied": 0, "failed": 0}
    assert any(method == "POST" and "/agent/ack?" in url for url, method in calls)


def test_safe_target_rejects_path_traversal(tmp_path):
    root = tmp_path / "hdd"
    root.mkdir()
    try:
        agent._safe_target(root, "../outside.mcrmbackup")
    except agent.AgentError:
        pass
    else:
        raise AssertionError("path traversal was accepted")
