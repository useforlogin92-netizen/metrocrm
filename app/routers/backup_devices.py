"""Super Admin-only external backup device approval and management."""
from __future__ import annotations

import html
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.ui_navigation import add_history_navigation
from app.database import get_db
from app.models import AuditEvent, User
from app.services.backup_devices import is_device_approved, list_devices, register_device, set_device_status
from app.config import settings

router = APIRouter(prefix="/admin/backups/devices", tags=["backup-devices"])


def require_super_admin(request: Request, db: Session) -> User:
    from app.main import _current_user
    user = _current_user(request, db)
    if not user or user.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return user


def require_agent(token: str | None) -> None:
    configured = settings.backup_agent_token.strip()
    if not configured or not token or not __import__("hmac").compare_digest(token, configured):
        raise HTTPException(status_code=401, detail="Backup agent authentication required")


@router.get("/", response_class=HTMLResponse)
def devices_page(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    devices = list_devices(db)
    rows = "".join(
        f"<tr><td><code>{html.escape(str(d['device_id']))}</code></td><td>{html.escape(str(d['device_name']))}</td><td>{html.escape(str(d.get('device_path') or ''))}</td><td><strong>{html.escape(str(d['status']))}</strong></td><td>"
        + (f"<form method='post' action='/admin/backups/devices/{html.escape(str(d['device_id']))}/approve' style='display:inline'><input type='hidden' name='csrf_token' value='{html.escape(__import__('app.csrf', fromlist=['csrf_token']).csrf_token(request))}'><button>Approve</button></form>" if d['status'] != 'APPROVED' else "")
        + (f" <form method='post' action='/admin/backups/devices/{html.escape(str(d['device_id']))}/revoke' style='display:inline'><input type='hidden' name='csrf_token' value='{html.escape(__import__('app.csrf', fromlist=['csrf_token']).csrf_token(request))}'><button>Revoke</button></form>" if d['status'] == 'APPROVED' else "")
        + "</td></tr>"
        for d in devices
    )
    return HTMLResponse(add_history_navigation(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Backup Devices · MetroCRM</title><style>body{{font-family:system-ui;background:#f4f7fb;color:#0f172a;padding:28px}}.wrap{{max-width:1100px;margin:auto}}.card{{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:20px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}button{{padding:7px 11px;border:0;border-radius:7px;cursor:pointer}}a{{text-decoration:none}}</style></head><body><div class='wrap'><div class='card'><h2>External Backup Devices</h2><p>Signed in as <strong>{html.escape(user.username)}</strong>. <strong>Only Super Admin</strong> can approve or revoke a device.</p><p><a href='/admin/backups/status'>← Backup Status</a></p><table><thead><tr><th>Device ID</th><th>Name</th><th>Path</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows or '<tr><td colspan=5>No devices registered yet.</td></tr>'}</tbody></table></div></div></body></html>"""))


@router.post("/{device_id}/approve", dependencies=[Depends(require_csrf)])
def approve_device(device_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    if not set_device_status(db, device_id, "APPROVED", user.id):
        raise HTTPException(status_code=404, detail="Backup device not found")
    db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_DEVICE_APPROVED", entity_type="BackupDevice", entity_id=device_id, details="Approved by Super Admin"))
    db.commit()
    return RedirectResponse("/admin/backups/devices/", status_code=303)


@router.post("/{device_id}/revoke", dependencies=[Depends(require_csrf)])
def revoke_device(device_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    if not set_device_status(db, device_id, "REVOKED", user.id):
        raise HTTPException(status_code=404, detail="Backup device not found")
    db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_DEVICE_REVOKED", entity_type="BackupDevice", entity_id=device_id, details="Revoked by Super Admin"))
    db.commit()
    return RedirectResponse("/admin/backups/devices/", status_code=303)


@router.post("/agent/register")
def register_agent_device(device_id: str, device_name: str, device_path: str = "", x_backup_agent_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_agent(x_backup_agent_token)
    if not device_id.strip() or len(device_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid backup device id")
    return register_device(db, device_id.strip(), device_name.strip() or device_id.strip(), device_path.strip())


@router.get("/agent/approved")
def agent_device_approved(device_id: str, x_backup_agent_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_agent(x_backup_agent_token)
    return {"device_id": device_id, "approved": is_device_approved(db, device_id)}
