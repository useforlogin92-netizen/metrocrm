"""Enforce dedicated browser-session boundaries between MetroCRM admin portals."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from app import main

app = main.app


def _required_portal(path: str) -> str | None:
    if path == "/admin" or path.startswith("/admin/"):
        return "admin"
    if path == "/super-admin" or path.startswith("/super-admin/"):
        return "super_admin"
    return None


@app.middleware("http")
async def enforce_dedicated_portal_session(request: Request, call_next):
    """Never let a session authenticated for one dedicated portal enter another."""
    required = _required_portal(request.url.path)
    if required:
        current_user_id = request.session.get("user_id")
        current_portal = request.session.get("login_portal")
        if current_user_id and current_portal != required:
            login_path = "/admin/login" if required == "admin" else "/super-admin/login"
            return RedirectResponse(login_path, status_code=303)
    return await call_next(request)
