"""Regression tests for Super Admin user-management permission override validation."""
from types import SimpleNamespace

from starlette.requests import Request

import app.main as main


def _request():
    path = "/admin/users/2/edit"
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
    })


class FakeDB:
    def __init__(self, target):
        self.target = target
        self.commits = 0

    def get(self, model, object_id):
        return self.target if object_id == self.target.id else None

    def commit(self):
        self.commits += 1


def _setup(monkeypatch, actor, target):
    db = FakeDB(target)
    monkeypatch.setattr(main, "_current_user", lambda request, session: actor)
    monkeypatch.setattr(main, "_can_manage_user", lambda actor, target=None, target_role=None: True)
    monkeypatch.setattr(main, "_valid_reporting_manager", lambda actor, manager_id, target, session: True)
    monkeypatch.setattr(main, "_audit", lambda *args, **kwargs: None)
    return db


def test_super_admin_can_save_valid_permission_overrides(monkeypatch):
    actor = SimpleNamespace(id=1, role="SUPER_ADMIN")
    target = SimpleNamespace(
        id=2, username="caller", role="TELECALLER", mobile=None, category=None,
        team=None, reporting_manager_id=None, email=None, permissions_json="{}",
    )
    db = _setup(monkeypatch, actor, target)

    response = main.edit_user(
        _request(), 2, "caller", "TELECALLER", "", "", "Sales", "Team A", "",
        '{"allow":{"leads":["VIEW"]},"deny":{"leads":["DELETE"]}}', db,
    )

    assert response.status_code == 303
    assert target.permissions_json == '{"allow":{"leads":["VIEW"]},"deny":{"leads":["DELETE"]}}'
    assert db.commits == 1


def test_invalid_permission_json_is_rejected_without_commit(monkeypatch):
    actor = SimpleNamespace(id=1, role="SUPER_ADMIN")
    target = SimpleNamespace(
        id=2, username="caller", role="TELECALLER", mobile=None, category=None,
        team=None, reporting_manager_id=None, email=None, permissions_json="{}",
    )
    db = _setup(monkeypatch, actor, target)

    response = main.edit_user(
        _request(), 2, "caller", "TELECALLER", "", "", "", "", "",
        '{"allow":{"leads":["ROOT_ACCESS"]}}', db,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users?error=permissions"
    assert db.commits == 0
    assert target.permissions_json == "{}"


def test_admin_cannot_change_permission_overrides(monkeypatch):
    actor = SimpleNamespace(id=1, role="ADMIN")
    target = SimpleNamespace(
        id=2, username="caller", role="TELECALLER", mobile=None, category=None,
        team=None, reporting_manager_id=None, email=None, permissions_json='{"deny":{"leads":["EDIT"]}}',
    )
    db = _setup(monkeypatch, actor, target)

    response = main.edit_user(
        _request(), 2, "caller", "TELECALLER", "", "", "", "", "",
        '{"allow":{"leads":["DELETE"]}}', db,
    )

    assert response.status_code == 303
    assert target.permissions_json == '{"deny":{"leads":["EDIT"]}}'
    assert db.commits == 1
