from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import unquote_plus

import pytest
from pydantic import ValidationError

from app.routers import open_source_project_search as search


def test_admin_and_super_admin_are_the_only_allowed_roles():
    assert search.ALLOWED_ROLES == {"ADMIN", "SUPER_ADMIN"}


def test_query_terms_include_location_side_status_developer_and_rera():
    query = search._query_terms({
        "city": "Mumbai",
        "locality": "Kandivali",
        "side": "East",
        "status": "upcoming",
        "developer": "Example Developer",
        "rera": "P51800012345",
    })
    assert "Mumbai" in query
    assert "Kandivali" in query
    assert "East" in query
    assert "upcoming" in query
    assert "Example Developer" in query
    assert "P51800012345" in query


def test_search_request_rejects_invalid_side_status_and_limit():
    with pytest.raises(ValidationError):
        search.ProjectSearchRequest(locality="Kandivali", side="North")
    with pytest.raises(ValidationError):
        search.ProjectSearchRequest(locality="Kandivali", status="unknown")
    with pytest.raises(ValidationError):
        search.ProjectSearchRequest(locality="Kandivali", limit=99)


def test_provider_missing_returns_source_links_without_saving_data(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setattr(search, "_actor", lambda request, db: SimpleNamespace(role="ADMIN", username="admin-test"))
    payload = search.ProjectSearchRequest(city="Mumbai", locality="Kandivali West", side="West", status="ready_to_move")
    result = search.search_open_source_projects(payload, request=object(), db=object())

    assert result["status"] == "provider_not_configured"
    assert result["results"] == []
    assert any(link["name"] == "MahaRERA project search" for link in result["links"])
    assert any(link["name"] == "Bing search" for link in result["links"])
    assert "no project data was saved" in result["message"].lower()


def test_non_admin_role_is_rejected(monkeypatch):
    monkeypatch.setattr(search, "_actor", lambda request, db: SimpleNamespace(role="MANAGER", username="manager-test"))
    payload = search.ProjectSearchRequest(locality="Kandivali")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        search.search_open_source_projects(payload, request=object(), db=object())
    assert exc.value.status_code == 403
