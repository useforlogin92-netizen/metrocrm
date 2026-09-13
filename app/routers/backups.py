"""Protected backup management endpoints."""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, User
from app.services.backup import acknowledge_agent_backup, backup_health, create_full_backup
from app.services.backup_restore import restore_backup

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin/backups", tags=["backups"])
legacy_super_admin_router = APIRouter(prefix="/super-admin/backups", tags=["backups"])


def require_super_admin(request: Request, db: Session) -> User:
    from app.main import _current_user
    user = _current_user(request, db)
    if not user or user.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return user


def require_backup_agent(token: str | None) -> None:
    configured = settings.backup_agent_token.strip()
    if not configured or not token or not hmac.compare_digest(token, configured):
        raise HTTPException(status_code=401, detail="Backup agent authentication required")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _oauth_json(url: str, payload: dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"OAuth provider rejected the request: {detail}") from exc


def _oauth_result_page(provider: str, refresh_token: str, folder_value: str) -> HTMLResponse:
    label = "Google Drive" if provider == "google" else "OneDrive"
    token_name = "BACKUP_GOOGLE_REFRESH_TOKEN" if provider == "google" else "BACKUP_ONEDRIVE_REFRESH_TOKEN"
    folder_name = "BACKUP_GOOGLE_FOLDER_ID" if provider == "google" else "BACKUP_ONEDRIVE_FOLDER_PATH"
    return HTMLResponse(f"""
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{label} OAuth complete</title>
<style>body{{font-family:system-ui;background:#f4f7fb;color:#0f172a;margin:0;padding:30px}}.wrap{{max-width:820px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:15px;padding:22px;margin-bottom:18px}}code{{display:block;background:#f8fafc;border:1px solid #e2e8f0;padding:12px;border-radius:9px;word-break:break-all}}.warn{{color:#9a3412}}a{{display:inline-block;padding:10px 14px;border-radius:9px;background:#2563eb;color:#fff;text-decoration:none;font-weight:800}}</style></head>
<body><div class='wrap'><div class='card'><h2>{label} authorization successful</h2><p>MetroCRM received the OAuth refresh token. It is <strong>not stored in the application database</strong>. Copy it into the deployment environment variable shown below.</p><h3>{token_name}</h3><code>{html.escape(refresh_token)}</code><h3>{folder_name}</h3><code>{html.escape(folder_value)}</code><p class='warn'><strong>Security:</strong> do not commit this token to GitHub or send it in chat/screenshots. After copying it to Render environment variables, restart/redeploy MetroCRM.</p><a href='/admin/backups/status'>Return to Backup Status</a></div></div></body></html>""")


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request, db: Session = Depends(get_db)):
    from app.main import _current_user
    user = _current_user(request, db)
    if not user:
        request.session.clear()
        return RedirectResponse("/super-admin/login", status_code=303)
    if user.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return templates.TemplateResponse("backup_status.html", {"request": request, "username": user.username, "role": user.role, "avatar": user.username[:1].upper(), "backup": backup_health(), "csrf_token": csrf_token(request), "backup_result": request.query_params.get("backup")})


@legacy_super_admin_router.get("/status")
def legacy_status():
    return RedirectResponse("/admin/backups/status", status_code=307)


@legacy_super_admin_router.get("/configure")
def legacy_configure(provider: str = ""):
    suffix = f"?provider={urllib.parse.quote(provider)}" if provider else ""
    return RedirectResponse(f"/admin/backups/configure{suffix}", status_code=307)


@router.get("/status.json")
def status_json(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    return {"user": user.username, **backup_health()}


@router.get("/configure", response_class=HTMLResponse)
def configure_page(request: Request, provider: str = "", db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    health = backup_health()
    google_ready = bool(settings.backup_google_client_id.strip() and settings.backup_google_client_secret.strip())
    onedrive_ready = bool(settings.backup_onedrive_client_id.strip() and settings.backup_onedrive_client_secret.strip())
    return HTMLResponse(f"""
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Backup Cloud Configuration · MetroCRM</title>
<style>body{{font-family:system-ui;background:#f4f7fb;color:#0f172a;margin:0;padding:30px}}.wrap{{max-width:900px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:15px;padding:22px;margin-bottom:18px}}a{{display:inline-block;padding:10px 14px;border-radius:9px;text-decoration:none;font-weight:800;background:#2563eb;color:#fff}}.muted{{color:#64748b;font-size:13px;line-height:1.6}}.ok{{color:#166534;font-weight:800}}.pending{{color:#9a3412;font-weight:800}}code{{background:#f8fafc;padding:2px 5px;border-radius:5px}}</style></head>
<body><div class='wrap'><div class='card'><h2>MetroCRM Cloud Backup Configuration</h2><p class='muted'>Signed in as <strong>{html.escape(user.username)}</strong>. Cloud secrets are never stored in the application database.</p><a href='/admin/backups/status'>← Back to Backup Status</a></div>
<div class='card'><h3>Google Drive</h3><p class='muted'>Status: <span class='{'ok' if health.get('google_drive_configured') else 'pending'}'>{'READY' if health.get('google_drive_configured') else 'CREDENTIALS PENDING'}</span></p><p class='muted'>Required: <code>BACKUP_GOOGLE_CLIENT_ID</code>, <code>BACKUP_GOOGLE_CLIENT_SECRET</code>, <code>BACKUP_GOOGLE_REFRESH_TOKEN</code>, <code>BACKUP_GOOGLE_FOLDER_ID</code>.</p>{"<a href='/admin/backups/google/connect'>Connect Google Drive</a>" if google_ready else "<span class='pending'>First add BACKUP_GOOGLE_CLIENT_ID and BACKUP_GOOGLE_CLIENT_SECRET in Render.</span>"}</div>
<div class='card'><h3>OneDrive</h3><p class='muted'>Status: <span class='{'ok' if health.get('onedrive_configured') else 'pending'}'>{'READY' if health.get('onedrive_configured') else 'CREDENTIALS PENDING'}</span></p><p class='muted'>Required: <code>BACKUP_ONEDRIVE_TENANT</code>, <code>BACKUP_ONEDRIVE_CLIENT_ID</code>, <code>BACKUP_ONEDRIVE_CLIENT_SECRET</code>, <code>BACKUP_ONEDRIVE_REFRESH_TOKEN</code>, <code>BACKUP_ONEDRIVE_FOLDER_PATH</code>.</p>{"<a href='/admin/backups/onedrive/connect'>Connect OneDrive</a>" if onedrive_ready else "<span class='pending'>First add BACKUP_ONEDRIVE_CLIENT_ID and BACKUP_ONEDRIVE_CLIENT_SECRET in Render.</span>"}</div>
<div class='card'><p class='muted'><strong>Redirect URIs for OAuth:</strong><br><code>/admin/backups/google/callback</code><br><code>/admin/backups/onedrive/callback</code><br>Register the complete HTTPS URL of your MetroCRM deployment with these paths.</p></div></div></body></html>""")


@router.get("/google/connect")
def google_connect(request: Request, db: Session = Depends(get_db)):
    require_super_admin(request, db)
    if not settings.backup_google_client_id.strip() or not settings.backup_google_client_secret.strip():
        raise HTTPException(status_code=409, detail="Google OAuth client ID and secret must be configured first")
    state = secrets.token_urlsafe(32)
    request.session["backup_google_oauth_state"] = state
    redirect_uri = str(request.base_url).rstrip("/") + "/admin/backups/google/callback"
    params = {"client_id": settings.backup_google_client_id, "redirect_uri": redirect_uri, "response_type": "code", "access_type": "offline", "prompt": "consent", "scope": "https://www.googleapis.com/auth/drive.file", "state": state}
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params), status_code=303)


@router.get("/google/callback", response_class=HTMLResponse)
def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    require_super_admin(request, db)
    expected = request.session.pop("backup_google_oauth_state", None)
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if error:
        raise HTTPException(status_code=400, detail=f"Google authorization failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Google authorization code missing")
    redirect_uri = str(request.base_url).rstrip("/") + "/admin/backups/google/callback"
    result = _oauth_json("https://oauth2.googleapis.com/token", {"client_id": settings.backup_google_client_id, "client_secret": settings.backup_google_client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    refresh_token = result.get("refresh_token")
    access_token = result.get("access_token")
    if not refresh_token or not access_token:
        raise HTTPException(status_code=502, detail="Google did not return the required offline refresh token")
    request_obj = urllib.request.Request("https://www.googleapis.com/drive/v3/files", data=json.dumps({"name": "MetroCRM-Backups", "mimeType": "application/vnd.google-apps.folder"}).encode(), headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request_obj, timeout=60) as response:
            folder = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"Google Drive folder creation failed: {detail}") from exc
    folder_id = folder.get("id")
    if not folder_id:
        raise HTTPException(status_code=502, detail="Google Drive did not return a folder id")
    return _oauth_result_page("google", refresh_token, folder_id)


@router.get("/onedrive/connect")
def onedrive_connect(request: Request, db: Session = Depends(get_db)):
    require_super_admin(request, db)
    if not settings.backup_onedrive_client_id.strip() or not settings.backup_onedrive_client_secret.strip():
        raise HTTPException(status_code=409, detail="OneDrive OAuth client ID and secret must be configured first")
    state = secrets.token_urlsafe(32)
    request.session["backup_onedrive_oauth_state"] = state
    tenant = settings.backup_onedrive_tenant.strip() or "common"
    redirect_uri = str(request.base_url).rstrip("/") + "/admin/backups/onedrive/callback"
    params = {"client_id": settings.backup_onedrive_client_id, "response_type": "code", "redirect_uri": redirect_uri, "response_mode": "query", "scope": "offline_access Files.ReadWrite User.Read", "state": state}
    return RedirectResponse(f"https://login.microsoftonline.com/{urllib.parse.quote(tenant, safe='')}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params), status_code=303)


@router.get("/onedrive/callback", response_class=HTMLResponse)
def onedrive_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    require_super_admin(request, db)
    expected = request.session.pop("backup_onedrive_oauth_state", None)
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if error:
        raise HTTPException(status_code=400, detail=f"Microsoft authorization failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Microsoft authorization code missing")
    tenant = settings.backup_onedrive_tenant.strip() or "common"
    redirect_uri = str(request.base_url).rstrip("/") + "/admin/backups/onedrive/callback"
    result = _oauth_json(f"https://login.microsoftonline.com/{urllib.parse.quote(tenant, safe='')}/oauth2/v2.0/token", {"client_id": settings.backup_onedrive_client_id, "client_secret": settings.backup_onedrive_client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri, "scope": "offline_access Files.ReadWrite User.Read"})
    refresh_token = result.get("refresh_token")
    access_token = result.get("access_token")
    if not refresh_token or not access_token:
        raise HTTPException(status_code=502, detail="Microsoft did not return the required offline refresh token")
    folder_name = settings.backup_onedrive_folder_path.strip().strip("/") or "MetroCRM-Backups"
    request_obj = urllib.request.Request("https://graph.microsoft.com/v1.0/me/drive/root/children", data=json.dumps({"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}).encode(), headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request_obj, timeout=60):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise HTTPException(status_code=502, detail=f"OneDrive folder creation failed: {detail}") from exc
    return _oauth_result_page("onedrive", refresh_token, folder_name)


@router.post("/run", dependencies=[Depends(require_csrf)])
def run_manual(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    try:
        result = create_full_backup("manual")
    except Exception as exc:
        db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_FAILED", entity_type="Backup", entity_id=None, details=str(exc)[:1000]))
        db.commit()
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/admin/backups/status?backup=failed", status_code=303)
        raise HTTPException(status_code=500, detail="Backup failed; check server backup logs") from exc
    action = "BACKUP_CREATED" if result.get("status") == "success" else "BACKUP_PARTIAL_FAILURE"
    db.add(AuditEvent(actor_user_id=user.id, action=action, entity_type="Backup", entity_id=None, details=str(result)[:4000]))
    db.commit()
    if "text/html" in request.headers.get("accept", ""):
        state = "success" if result.get("status") == "success" else "partial"
        return RedirectResponse(f"/admin/backups/status?backup={state}", status_code=303)
    return result


@router.post("/restore", dependencies=[Depends(require_csrf)])
def restore(request: Request, relative_path: str, confirmation: str, expected_sha256: str | None = None, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    if confirmation != "RESTORE":
        raise HTTPException(status_code=400, detail="Explicit RESTORE confirmation required")
    root = Path(settings.backup_local_path).expanduser().resolve()
    package = (root / relative_path).resolve()
    if root not in package.parents or package.suffix != ".mcrmbackup" or not package.is_file():
        raise HTTPException(status_code=404, detail="Backup file not found")
    try:
        result = restore_backup(package, expected_sha256=expected_sha256)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_RESTORE_FAILED", entity_type="Backup", entity_id=None, details=str(exc)[:2000]))
        db.commit()
        raise HTTPException(status_code=400, detail="Backup restore failed; check backup integrity and server logs") from exc
    db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_RESTORED", entity_type="Backup", entity_id=None, details=str(result)[:4000]))
    db.commit()
    return result


@router.get("/agent/manifest")
def agent_manifest(x_backup_agent_token: str | None = Header(default=None)):
    require_backup_agent(x_backup_agent_token)
    root = Path(settings.backup_local_path).expanduser().resolve()
    if not root.exists():
        return {"files": []}
    files = []
    for path in sorted(root.rglob("*.mcrmbackup")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            stat = path.stat()
            files.append({"path": relative, "size": stat.st_size, "modified": stat.st_mtime_ns, "sha256": _sha256(path)})
    return {"files": files}


@router.get("/agent/file/{relative_path:path}")
def agent_file(relative_path: str, x_backup_agent_token: str | None = Header(default=None)):
    require_backup_agent(x_backup_agent_token)
    root = Path(settings.backup_local_path).expanduser().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix != ".mcrmbackup":
        raise HTTPException(status_code=404, detail="Backup file not found")
    return FileResponse(target, filename=target.name, media_type="application/octet-stream")


@router.post("/agent/ack")
def agent_ack(relative_path: str, x_backup_agent_token: str | None = Header(default=None)):
    require_backup_agent(x_backup_agent_token)
    if not acknowledge_agent_backup(relative_path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    return {"status": "success", "path": relative_path}
