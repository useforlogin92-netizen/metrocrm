"""Protected backup management endpoints."""
from __future__ import annotations

import hashlib
import hmac
import html
from pathlib import Path
from urllib.parse import quote_plus

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


@router.get("/status.json")
def status_json(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    return {"user": user.username, **backup_health()}


@router.get("/configure", response_class=HTMLResponse)
def configure_page(request: Request, provider: str = "", db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    selected = provider.lower().strip()
    if selected not in {"google_drive", "onedrive"}:
        selected = ""
    health = backup_health()
    google_ready_for_oauth = bool(settings.backup_google_client_id.strip() and settings.backup_google_client_secret.strip())
    onedrive_ready_for_oauth = bool(settings.backup_onedrive_client_id.strip() and settings.backup_onedrive_client_secret.strip())
    return HTMLResponse(f"""
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Backup Cloud Configuration · MetroCRM</title>
<style>body{{font-family:system-ui;background:#f4f7fb;color:#0f172a;margin:0;padding:30px}}.wrap{{max-width:900px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:15px;padding:22px;margin-bottom:18px}}a,button{{display:inline-block;padding:10px 14px;border-radius:9px;text-decoration:none;font-weight:800;border:0;cursor:pointer}}.primary{{background:#2563eb;color:#fff}}.muted{{color:#64748b;font-size:13px;line-height:1.6}}.ok{{color:#166534;font-weight:800}}.pending{{color:#9a3412;font-weight:800}}code{{background:#f8fafc;padding:2px 5px;border-radius:5px}}</style></head>
<body><div class='wrap'><div class='card'><h2>MetroCRM Cloud Backup Configuration</h2><p class='muted'>Signed in as <strong>{html.escape(user.username)}</strong>. Cloud credentials are deployment secrets and are never saved in the application database.</p><a class='primary' href='/admin/backups/status'>← Back to Backup Status</a></div>
<div class='card'><h3>Google Drive</h3><p class='muted'>Status: <span class='{'ok' if health.get('google_drive_configured') else 'pending'}'>{'READY' if health.get('google_drive_configured') else 'CREDENTIALS PENDING'}</span></p><p class='muted'>Required Render environment variables: <code>BACKUP_GOOGLE_CLIENT_ID</code>, <code>BACKUP_GOOGLE_CLIENT_SECRET</code>, <code>BACKUP_GOOGLE_REFRESH_TOKEN</code>, <code>BACKUP_GOOGLE_FOLDER_ID</code>.</p><p class='muted'>First create a Google OAuth Web Application client and authorize Drive access. Google requires an OAuth client and an exact authorized redirect URI for a web-server flow. urlGoogle OAuth documentationhttps://developers.google.com/identity/protocols/oauth2/web-server</p>{"<a class='primary' href='/admin/backups/google/connect'>Start Google OAuth</a>" if google_ready_for_oauth else "<span class='pending'>OAuth client ID/secret are not configured in Render yet.</span>"}</div>
<div class='card'><h3>OneDrive</h3><p class='muted'>Status: <span class='{'ok' if health.get('onedrive_configured') else 'pending'}'>{'READY' if health.get('onedrive_configured') else 'CREDENTIALS PENDING'}</span></p><p class='muted'>Required Render environment variables: <code>BACKUP_ONEDRIVE_TENANT</code>, <code>BACKUP_ONEDRIVE_CLIENT_ID</code>, <code>BACKUP_ONEDRIVE_CLIENT_SECRET</code>, <code>BACKUP_ONEDRIVE_REFRESH_TOKEN</code>, <code>BACKUP_ONEDRIVE_FOLDER_PATH</code>.</p><p class='muted'>Register a Microsoft Entra application and configure its Web redirect URI before authorizing OneDrive.</p>{"<a class='primary' href='/admin/backups/onedrive/connect'>Start OneDrive OAuth</a>" if onedrive_ready_for_oauth else "<span class='pending'>Microsoft client ID/secret are not configured in Render yet.</span>"}</div>
<div class='card'><h3>Important</h3><p class='muted'>Do not paste client secrets or refresh tokens into GitHub, chat, screenshots, or the application database. Put them only in the deployment environment variables. After changing Render environment variables, redeploy/restart MetroCRM and refresh this page.</p></div></div></body></html>""")


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
    """Restore the selected encrypted backup into the configured live database."""
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
