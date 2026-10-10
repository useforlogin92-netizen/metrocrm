from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routers import caller_search


def _request(path="/caller/search", method="GET"):
    return Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b"", "session": {}})


@pytest.mark.parametrize("role", ["SALES_EXECUTIVE", "TELECALLER", "TL", "MANAGER", "ADMIN", "SUPER_ADMIN"])
def test_sales_and_management_roles_can_use_property_search(role):
    assert caller_search._can_use_search(SimpleNamespace(role=role))


@pytest.mark.parametrize("role", ["ACCOUNTANT", "USER", "STAFF"])
def test_unrelated_roles_cannot_use_property_search(role, monkeypatch, db_session):
    actor = SimpleNamespace(role=role, username="non-sales", id=99)
    monkeypatch.setattr(caller_search, "_user", lambda request, db: actor)

    with pytest.raises(HTTPException) as exc:
        caller_search.caller_search_options(_request(), db_session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "caller_search_not_permitted"
    page = caller_search.caller_search_page(_request(), db_session)
    assert page.status_code == 303


def test_sales_executive_property_search_post_is_allowed_to_reach_search_logic(monkeypatch, db_session):
    actor = SimpleNamespace(role="SALES_EXECUTIVE", username="sales-exec", id=12)
    monkeypatch.setattr(caller_search, "_user", lambda request, db: actor)
    monkeypatch.setattr(caller_search, "_inventory_rows", lambda db, city: [])
    body = caller_search.CallerSearchRequest(city="Mumbai")

    response = caller_search.caller_search(body, _request(method="POST"), db_session)

    assert response == {"count": 0, "results": []}
