from types import SimpleNamespace

from starlette.requests import Request

from app.permissions import Access, Role, role_allows
from app.routers import accounting


def _request():
    return Request({"type": "http", "method": "GET", "path": "/accounting", "headers": [], "query_string": b""})


def test_accountant_can_access_register_but_not_admin_only_controls(monkeypatch, db_session):
    accountant = SimpleNamespace(id=10, role="ACCOUNTANT", username="finance-user")
    monkeypatch.setattr("app.main._current_user", lambda request, db: accountant)

    assert accounting.actor(_request(), db_session) is accountant
    assert accounting.admin_actor(_request(), db_session) is None
    assert role_allows(Role.ACCOUNTANT, "accounting", Access.VIEW)
    assert role_allows(Role.ACCOUNTANT, "accounting", Access.CREATE)
    assert role_allows(Role.ACCOUNTANT, "accounting", Access.EXPORT)
    assert not role_allows(Role.ACCOUNTANT, "accounting", Access.DELETE)


def test_admin_finance_controls_remain_available(monkeypatch, db_session):
    admin = SimpleNamespace(id=11, role="ADMIN", username="finance-admin")
    monkeypatch.setattr("app.main._current_user", lambda request, db: admin)

    assert accounting.actor(_request(), db_session) is admin
    assert accounting.admin_actor(_request(), db_session) is admin



def test_accountant_cannot_open_admin_only_journal_page(monkeypatch, db_session):
    accountant = SimpleNamespace(id=12, role="ACCOUNTANT", username="finance-user")
    monkeypatch.setattr("app.main._current_user", lambda request, db: accountant)

    response = accounting.journal_page(_request(), db_session)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
