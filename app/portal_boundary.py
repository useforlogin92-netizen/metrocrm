"""Enforce dedicated browser-session and sensitive-operation boundaries."""
from __future__ import annotations

from html import escape

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app import main
from app.csrf import csrf_token, require_csrf
from app.database import get_db

app = main.app


def _required_portal(path: str) -> str | None:
    if path == "/admin" or path.startswith("/admin/"):
        return "admin"
    if path == "/super-admin" or path.startswith("/super-admin/"):
        return "super_admin"
    return None


def _is_portal_login(path: str, required: str) -> bool:
    return path == ("/admin/login" if required == "admin" else "/super-admin/login")


def _sensitive_export_get(request: Request) -> HTMLResponse | None:
    """Turn legacy export GET links into explicit CSRF-protected POST forms."""
    path = request.url.path
    if getattr(request, "method", "GET") != "GET":
        return None
    csrf = escape(csrf_token(request), quote=True)
    if path.startswith("/admin/data-tools/export/"):
        entity = escape(path.rsplit("/", 1)[-1], quote=True)
        params = getattr(request, "query_params", {})
        request_id = params.get("request_id")
        safe_request_id = escape(str(request_id), quote=True) if request_id else None
        query = f"?request_id={safe_request_id}" if safe_request_id else ""
        action = escape(f"/admin/data-tools/export/{entity}{query}", quote=True)
        body = (
            "<!doctype html><html><body><h1>Confirm data export</h1>"
            "<p>This sensitive operation requires an explicit POST request.</p>"
            f"<form method='post' action='{action}'>"
            f"<input type='hidden' name='csrf_token' value='{csrf}'>"
            "<button type='submit'>Continue to export</button></form>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    if path.startswith("/super-admin/data-export-requests/") and path.endswith("/download"):
        request_id = escape(path.split("/")[3], quote=True)
        action = escape(f"/super-admin/data-export-requests/{request_id}/download", quote=True)
        body = (
            "<!doctype html><html><body><h1>Confirm data export</h1>"
            "<p>This sensitive operation requires an explicit POST request.</p>"
            f"<form method='post' action='{action}'>"
            f"<input type='hidden' name='csrf_token' value='{csrf}'>"
            "<button type='submit'>Continue to export</button></form>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    if path == "/admin/property-data/export":
        body = (
            "<!doctype html><html><body><h1>Confirm property data export</h1>"
            "<p>This sensitive operation requires an explicit POST request.</p>"
            "<form method='post' action='/admin/property-data/export'>"
            f"<input type='hidden' name='csrf_token' value='{csrf}'>"
            "<button type='submit'>Continue to export</button></form>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    if path.startswith("/admin/property-data/export/download/"):
        request_id = escape(path.rsplit("/", 1)[-1], quote=True)
        action = escape(f"/admin/property-data/export/download/{request_id}", quote=True)
        body = (
            "<!doctype html><html><body><h1>Confirm property data export</h1>"
            "<p>This sensitive operation requires an explicit POST request.</p>"
            f"<form method='post' action='{action}'>"
            f"<input type='hidden' name='csrf_token' value='{csrf}'>"
            "<button type='submit'>Continue to export</button></form>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    return None


@app.middleware("http")
async def enforce_dedicated_portal_session(request: Request, call_next):
    """Never let a session authenticated for one dedicated portal enter another."""
    required = _required_portal(request.url.path)
    if required and not _is_portal_login(request.url.path, required):
        current_user_id = request.session.get("user_id")
        current_portal = request.session.get("login_portal")
        if current_user_id and current_portal != required:
            login_path = "/admin/login" if required == "admin" else "/super-admin/login"
            return RedirectResponse(login_path, status_code=303)
    export_get = _sensitive_export_get(request)
    if export_get is not None:
        return export_get
    return await call_next(request)


# Add POST aliases for the existing export handlers. The original GET handlers
# remain in the legacy router, but the middleware above prevents them from running.
from app.routers.data_tools import export_data as _legacy_export_data
from app.routers.data_tools import super_admin_download_export as _legacy_super_admin_download_export
from app.routers.property_data import export_property_data as _legacy_export_property_data
from app.routers.property_data import download_approved_property_export as _legacy_download_approved_property_export


@app.post("/admin/data-tools/export/{entity_type}", dependencies=[Depends(require_csrf)])
def export_data_post(request: Request, entity_type: str, request_id: int | None = None, db=Depends(get_db)):
    return _legacy_export_data(request=request, entity_type=entity_type, request_id=request_id, db=db)


@app.post("/super-admin/data-export-requests/{request_id}/download", dependencies=[Depends(require_csrf)])
def super_admin_download_export_post(request_id: int, request: Request, db=Depends(get_db)):
    return _legacy_super_admin_download_export(request_id=request_id, request=request, db=db)


@app.post("/admin/property-data/export", dependencies=[Depends(require_csrf)])
def export_property_data_post(request: Request, db=Depends(get_db)):
    return _legacy_export_property_data(request=request, db=db)


@app.post("/admin/property-data/export/download/{request_id}", dependencies=[Depends(require_csrf)])
def download_approved_property_export_post(request_id: int, request: Request, db=Depends(get_db)):
    return _legacy_download_approved_property_export(request=request, request_id=request_id, db=db)


# FastAPI's decorator middleware is inserted at the front of user_middleware.
# Keep SessionMiddleware outermost so the boundary can safely inspect the session
# while preserving the existing idle-session middleware ordering contract.
for _index, _middleware in enumerate(app.user_middleware):
    if _middleware.cls is SessionMiddleware:
        if _index:
            app.user_middleware.insert(0, app.user_middleware.pop(_index))
        break
