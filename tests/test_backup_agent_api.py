import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException


def _prepare_backup(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.backup import create_full_backup

    database = tmp_path / "metrocrm.db"
    conn = sqlite3.connect(database)
    conn.execute("create table data (id integer primary key, value text)")
    conn.execute("insert into data(value) values ('agent-test')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database}")
    monkeypatch.setattr(settings, "backup_local_path", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "uploads_path", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "backup_encryption_key", "agent-api-test-secret")
    monkeypatch.setattr(settings, "backup_agent_token", "agent-secret")
    monkeypatch.setattr(settings, "backup_external_path", "")
    monkeypatch.setattr(settings, "backup_cloud_provider", "none")
    monkeypatch.setattr(settings, "backup_cloud_providers", "")
    return create_full_backup("agent-test")


def test_backup_agent_manifest_requires_token(monkeypatch, tmp_path):
    from app.config import settings
    from app.routers.backups import agent_manifest

    monkeypatch.setattr(settings, "backup_local_path", str(tmp_path))
    monkeypatch.setattr(settings, "backup_agent_token", "agent-secret")

    with pytest.raises(HTTPException) as exc:
        agent_manifest("wrong")
    assert exc.value.status_code == 401


def test_backup_agent_manifest_reports_sha256(monkeypatch, tmp_path):
    result = _prepare_backup(monkeypatch, tmp_path)
    from app.routers.backups import agent_manifest

    payload = agent_manifest("agent-secret")
    assert len(payload["files"]) == 1
    item = payload["files"][0]
    path = Path(result["local_path"])
    assert item["path"] == f"{result['date']}/{path.name}"
    assert item["size"] == path.stat().st_size
    assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_backup_agent_file_rejects_path_traversal(monkeypatch, tmp_path):
    _prepare_backup(monkeypatch, tmp_path)
    from app.routers.backups import agent_file

    with pytest.raises(HTTPException) as exc:
        agent_file("../outside.mcrmbackup", "agent-secret")
    assert exc.value.status_code == 404


def test_backup_agent_ack_marks_delivery(monkeypatch, tmp_path):
    result = _prepare_backup(monkeypatch, tmp_path)
    from app.config import settings
    from app.routers.backups import agent_ack
    from app.services.backup import _read_state, _state_path

    relative = f"{result['date']}/{Path(result['local_path']).name}"
    response = agent_ack(relative, "agent-secret")
    assert response == {"status": "success", "path": relative}

    state = _read_state(_state_path(relative))
    assert state is not None
    assert state["destinations"]["agent_pc"]["status"] == "success"
    assert state["status"] == "success"
    assert settings.backup_agent_token == "agent-secret"
