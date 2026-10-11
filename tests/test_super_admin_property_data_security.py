from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.main import app
from app.routers import property_data


def _request():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "server": ("testserver", 80), "client": ("127.0.0.1", 1234), "scheme": "http"})


def test_property_data_routes_are_registered_for_both_portals():
    paths = {route.path for route in app.routes}
    assert "/admin/property-data" in paths
    assert "/super-admin/property-data" in paths
    assert "/admin/property-data/template" in paths
    assert "/super-admin/property-data/template" in paths
    assert "/admin/property-data/import" in paths
    assert "/super-admin/property-data/import" in paths
    assert "/super-admin/property-data/delete-godrej-nest" in paths


def test_godrej_nest_delete_route_is_post_only_and_super_admin_scoped():
    routes = [
        route for route in app.routes
        if getattr(route, "path", None) == "/super-admin/property-data/delete-godrej-nest"
    ]
    assert routes
    assert all(route.methods == {"POST"} for route in routes)


@pytest.mark.parametrize("role", ["TELECALLER", "SALES_EXECUTIVE", "MANAGER", "TL", "ACCOUNTANT", "HR"])
def test_property_data_guard_rejects_non_admin_roles(monkeypatch, role):
    monkeypatch.setattr(property_data, "_user", lambda request, db: SimpleNamespace(role=role))
    with pytest.raises(HTTPException) as exc:
        property_data._guard(_request(), object())
    assert exc.value.status_code == 403


def test_property_data_guard_requires_authentication(monkeypatch):
    monkeypatch.setattr(property_data, "_user", lambda request, db: None)
    with pytest.raises(HTTPException) as exc:
        property_data._guard(_request(), object())
    assert exc.value.status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "SUPER_ADMIN"])
def test_property_data_guard_allows_admin_roles(monkeypatch, role):
    actor = SimpleNamespace(role=role)
    monkeypatch.setattr(property_data, "_user", lambda request, db: actor)
    assert property_data._guard(_request(), object()) is actor
