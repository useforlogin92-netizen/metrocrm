"""Regression tests for Super Admin using the shared/legacy WhatsApp import URL."""
import asyncio
from types import SimpleNamespace

from starlette.requests import Request

import app.routers.whatsapp_property_import as routes


def _request(path: str, method: str = "POST") -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
    })


def test_shared_admin_analyze_url_dispatches_super_admin_to_super_admin_workflow(monkeypatch):
    actor = SimpleNamespace(role="SUPER_ADMIN")
    monkeypatch.setattr(routes, "_guard", lambda request, db: actor)
    calls = []

    async def fake_analyze(request, source_text, files, db, role):
        calls.append(role)
        return "handled"

    monkeypatch.setattr(routes, "_analyze", fake_analyze)
    result = asyncio.run(routes.admin_analyze(
        _request("/admin/property-data/whatsapp-import/analyze"),
        source_text="Project details",
        files=[],
        db=object(),
    ))

    assert result == "handled"
    assert calls == ["SUPER_ADMIN"]


def test_shared_admin_analyze_url_keeps_admin_in_admin_workflow(monkeypatch):
    actor = SimpleNamespace(role="ADMIN")
    monkeypatch.setattr(routes, "_guard", lambda request, db: actor)
    calls = []

    async def fake_analyze(request, source_text, files, db, role):
        calls.append(role)
        return "handled"

    monkeypatch.setattr(routes, "_analyze", fake_analyze)
    asyncio.run(routes.admin_analyze(
        _request("/admin/property-data/whatsapp-import/analyze"),
        source_text="Project details",
        files=[],
        db=object(),
    ))

    assert calls == ["ADMIN"]


def test_super_admin_get_on_legacy_admin_queue_redirects_to_super_admin_queue(monkeypatch):
    actor = SimpleNamespace(role="SUPER_ADMIN")
    monkeypatch.setattr(routes, "_guard", lambda request, db: actor)
    response = routes.admin_page(
        _request("/admin/property-data/whatsapp-import", method="GET"),
        db=object(),
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/super-admin/property-data/whatsapp-import"
