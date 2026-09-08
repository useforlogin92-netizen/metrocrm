"""Protected backup management endpoints."""
from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, User
from app.services.backup import backup_health, create_full_backup

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


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    return request.app.state.templates.TemplateResponse(
        "backup_status.html",
        {
            "request": request,
            "username": user.username,
            "role": user.role,
            "avatar": user.username[:1].upper(),
            "backup": backup_health(),
            "csrf_token": csrf_token(request),
        },
    )


@router.get("/status.json")
def status_json(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    return {"user": user.username, **backup_health()}


@router.post("/run", dependencies=[Depends(require_csrf)])
def run_manual(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    try:
        result = create_full_backup("manual")
    except Exception as exc:
        db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_FAILED", entity_type="Backup", entity_id=None, details=str(exc)[:1000]))
        db.commit()
        raise HTTPException(status_code=500, detail="Backup failed; check server backup logs") from exc
    action = "BACKUP_CREATED" if result.get("status") == "success" else "BACKUP_PARTIAL_FAILURE"
    db.add(AuditEvent(actor_user_id=user.id, action=action, entity_type="Backup", entity_id=None, details=str(result)[:4000]))
    db.commit()
    return result


@router.get("/agent/manifest")
def agent_manifest(x_backup_agent_token: str | None = Header(default=None)):
    """Return encrypted backup files available for a trusted desktop backup agent."""
    require_backup_agent(x_backup_agent_token)
    root = Path(settings.backup_local_path).expanduser().resolve()
    if not root.exists():
        return {"files": []}
    files = []
    for path in sorted(root.rglob("*.mcrmbackup")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            stat = path.stat()
            files.append({"path": relative, "size": stat.st_size, "modified": stat.st_mtime_ns})
    return {"files": files}


@router.get("/agent/file/{relative_path:path}")
def agent_file(relative_path: str, x_backup_agent_token: str | None = Header(default=None)):
    """Download one encrypted backup to a trusted local backup agent."""
    require_backup_agent(x_backup_agent_token)
    root = Path(settings.backup_local_path).expanduser().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix != ".mcrmbackup":
        raise HTTPException(status_code=404, detail="Backup file not found")
    return FileResponse(target, filename=target.name, media_type="application/octet-stream")
