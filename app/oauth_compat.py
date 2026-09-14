"""Production OAuth compatibility routes for legacy Super Admin backup URLs."""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from app.main_portal import app
from app.routers.backups import _oauth_json, _oauth_result_page, require_super_admin, run_manual


@app.get("/super-admin/backups/google/connect")
def legacy_google_connect(request: Request, db: Session = Depends(get_db)):
    """Start Google OAuth using the legacy callback URI with a resilient state cookie."""
    require_super_admin(request, db)
    if not settings.backup_google_client_id.strip() or not settings.backup_google_client_secret.strip():
        raise HTTPException(status_code=409, detail="Google OAuth client ID and secret must be configured first")
    state = secrets.token_urlsafe(32)
    request.session["backup_google_oauth_state"] = state
    redirect_uri = str(request.base_url).rstrip("/") + "/super-admin/backups/google/callback"
    params = {"client_id": settings.backup_google_client_id, "redirect_uri": redirect_uri, "response_type": "code", "access_type": "offline", "prompt": "consent", "scope": "https://www.googleapis.com/auth/drive.file", "state": state}
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params), status_code=303)
    response.set_cookie("metrocrm_google_oauth_state", state, max_age=600, httponly=True, secure=True, samesite="lax", path="/")
    return response


@app.get("/super-admin/backups/google/callback", response_class=HTMLResponse)
def legacy_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Handle legacy Google callbacks while accepting the resilient state cookie fallback."""
    require_super_admin(request, db)
    expected_session = request.session.pop("backup_google_oauth_state", None)
    expected_cookie = request.cookies.get("metrocrm_google_oauth_state")
    if expected_session and expected_cookie and not secrets.compare_digest(expected_session, expected_cookie):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    expected = expected_session or expected_cookie
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if error:
        raise HTTPException(status_code=400, detail=f"Google authorization failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Google authorization code missing")

    redirect_uri = str(request.base_url).rstrip("/") + "/super-admin/backups/google/callback"
    result = _oauth_json(
        "https://oauth2.googleapis.com/token",
        {
            "client_id": settings.backup_google_client_id,
            "client_secret": settings.backup_google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    refresh_token = result.get("refresh_token")
    access_token = result.get("access_token")
    if not refresh_token or not access_token:
        raise HTTPException(status_code=502, detail="Google did not return the required offline refresh token")

    request_obj = urllib.request.Request(
        "https://www.googleapis.com/drive/v3/files",
        data=json.dumps({"name": "MetroCRM-Backups", "mimeType": "application/vnd.google-apps.folder"}).encode(),
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=60) as response:
            folder = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"Google Drive folder creation failed: {detail}") from exc
    folder_id = folder.get("id")
    if not folder_id:
        raise HTTPException(status_code=502, detail="Google Drive did not return a folder id")
    response = _oauth_result_page("google", refresh_token, folder_id)
    response.delete_cookie("metrocrm_google_oauth_state", path="/")
    return response


@app.get("/super-admin/backups/run")
def legacy_run_backup_get(request: Request, db: Session = Depends(get_db)):
    """Never expose a misleading 405 page for a stale/legacy GET URL."""
    require_super_admin(request, db)
    return RedirectResponse("/admin/backups/status", status_code=303)


@app.post("/super-admin/backups/run", dependencies=[Depends(require_csrf)])
def legacy_run_backup(request: Request, db: Session = Depends(get_db)):
    """Preserve the legacy Super Admin backup URL as a safe POST endpoint."""
    return run_manual(request, db)
