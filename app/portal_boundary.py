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


# Legacy Admin URLs that are still used by the shared dashboard/navigation.
# Super Admin users must see/use a dedicated /super-admin URL instead of being
# redirected into the Admin login portal.
_SUPER_ADMIN_LEGACY_ROUTES = (
    ("/admin/users/pending", "/super-admin/users/pending"),
    ("/admin/users", "/super-admin/users"),
    ("/admin/property-data/social", "/super-admin/property-data/social"),
    ("/admin/property-data", "/super-admin/property-data"),
    ("/admin/property-submissions", "/super-admin/property-submissions"),
    ("/admin/leads/offline-import", "/super-admin/leads/offline-import"),
    ("/admin/data-tools", "/super-admin/data-tools"),
    ("/admin/backups", "/super-admin/backups"),
    ("/admin/business-reports", "/super-admin/business-reports"),
)


def _required_portal(path: str) -> str | None:
    if path == "/super-admin" or path.startswith("/super-admin/"):
        return "super_admin"
    if path == "/admin" or path.startswith("/admin/"):
        return "admin"
    return None


def _is_portal_login(path: str, required: str) -> bool:
    return path == ("/admin/login" if required == "admin" else "/super-admin/login")


def _super_admin_redirect_for_legacy_admin_path(path: str) -> str | None:
    for legacy, dedicated in _SUPER_ADMIN_LEGACY_ROUTES:
        if path == legacy or path.startswith(legacy + "/"):
            return dedicated + path[len(legacy):]
    return None


def _rewrite_super_admin_location(location: str | None) -> str | None:
    """Rewrite handler redirects so a Super Admin never lands on an /admin URL."""
    if not location:
        return None
    for legacy, dedicated in _SUPER_ADMIN_LEGACY_ROUTES:
        if location == legacy or location.startswith(legacy + "/") or location.startswith(legacy + "?"):
            return dedicated + location[len(legacy):]
    return None


def _super_admin_legacy_route_bridge(request: Request) -> bool:
    """Run legacy Admin handlers behind dedicated Super Admin URLs."""
    if request.session.get("login_portal") != "super_admin":
        return False
    path = request.url.path
    for legacy, dedicated in _SUPER_ADMIN_LEGACY_ROUTES:
        if path == dedicated or path.startswith(dedicated + "/"):
            legacy_path = legacy + path[len(dedicated):]
            request.scope["path"] = legacy_path
            request.scope["raw_path"] = legacy_path.encode("ascii")
            return True
    return False


def _rewrite_super_admin_user_management_links(response: HTMLResponse) -> HTMLResponse:
    """Expose the dedicated URL in rendered Super Admin user-management HTML."""
    response.body = response.body.replace(b"/admin/users", b"/super-admin/users")
    if "content-length" in response.headers:
        del response.headers["content-length"]
    return response


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
        body = ("<!doctype html><html><body><h1>Confirm data export</h1>"
                "<p>This sensitive operation requires an explicit POST request.</p>"
                f"<form method='post' action='{action}'>"
                f"<input type='hidden' name='csrf_token' value='{csrf}'>"
                "<button type='submit'>Continue to export</button></form></body></html>")
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    if path.startswith("/super-admin/data-export-requests/") and path.endswith("/download"):
        request_id = escape(path.split("/")[3], quote=True)
        action = escape(f"/super-admin/data-export-requests/{request_id}/download", quote=True)
        body = ("<!doctype html><html><body><h1>Confirm data export</h1>"
                "<p>This sensitive operation requires an explicit POST request.</p>"
                f"<form method='post' action='{action}'>"
                f"<input type='hidden' name='csrf_token' value='{csrf}'>"
                "<button type='submit'>Continue to export</button></form></body></html>")
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    if path == "/admin/property-data/export":
        body = ("<!doctype html><html><body><h1>Confirm property data export</h1>"
                "<p>This sensitive operation requires an explicit POST request.</p>"
                "<form method='post' action='/admin/property-data/export'>"
                f"<input type='hidden' name='csrf_token' value='{csrf}'>"
                "<button type='submit'>Continue to export</button></form></body></html>")
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    if path.startswith("/admin/property-data/export/download/"):
        request_id = escape(path.rsplit("/", 1)[-1], quote=True)
        action = escape(f"/admin/property-data/export/download/{request_id}", quote=True)
        body = ("<!doctype html><html><body><h1>Confirm property data export</h1>"
                "<p>This sensitive operation requires an explicit POST request.</p>"
                f"<form method='post' action='{action}'>"
                f"<input type='hidden' name='csrf_token' value='{csrf}'>"
                "<button type='submit'>Continue to export</button></form></body></html>")
        return HTMLResponse(body, status_code=405, headers={"Allow": "POST"})
    return None


@app.middleware("http")
async def enforce_dedicated_portal_session(request: Request, call_next):
    """Keep Admin and Super Admin sessions strictly isolated."""
    original_path = request.url.path
    current_portal = request.session.get("login_portal")
    legacy_super_admin_post = False

    if current_portal == "super_admin":
        dedicated_path = _super_admin_redirect_for_legacy_admin_path(original_path)
        if dedicated_path:
            # GET/HEAD can safely redirect to the dedicated browser namespace.
            # POST must NOT be redirected with 303 because that converts the
            # form submission into a GET and produces a misleading 405.
            if request.method in {"GET", "HEAD"}:
                return RedirectResponse(dedicated_path, status_code=303)
            legacy_super_admin_post = True

    required = _required_portal(original_path)
    if required and not _is_portal_login(original_path, required):
        current_user_id = request.session.get("user_id")
        if current_user_id and current_portal != required and not legacy_super_admin_post:
            # A Super Admin must never be sent to the Admin login portal.
            # If an old/unmapped Admin URL is reached from a Super Admin
            # session, keep the browser inside the privileged namespace.
            if current_portal == "super_admin" and required == "admin":
                return RedirectResponse("/super-admin", status_code=303)
            login_path = "/admin/login" if required == "admin" else "/super-admin/login"
            return RedirectResponse(login_path, status_code=303)

    export_get = _sensitive_export_get(request)
    if export_get is not None:
        return export_get

    bridge_active = _super_admin_legacy_route_bridge(request)
    response = await call_next(request)

    # Legacy handlers still return /admin/* redirects. Keep those redirects on
    # the dedicated Super Admin surface so the browser never visibly crosses
    # into the Admin portal.
    if current_portal == "super_admin" and isinstance(response, RedirectResponse):
        dedicated_location = _rewrite_super_admin_location(response.headers.get("location"))
        if dedicated_location:
            response.headers["location"] = dedicated_location

    if bridge_active and isinstance(response, HTMLResponse):
        response = _rewrite_super_admin_user_management_links(response)
    return response


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


for _index, _middleware in enumerate(app.user_middleware):
    if _middleware.cls is SessionMiddleware:
        if _index:
            app.user_middleware.insert(0, app.user_middleware.pop(_index))
        break
