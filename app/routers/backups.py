"""Protected backup management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditEvent, User
from app.services.backup import backup_health, create_full_backup

router = APIRouter(prefix="/admin/backups", tags=["backups"])


def require_super_admin(request: Request, db: Session) -> User:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active or user.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return user


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    return {"user": user.username, **backup_health()}


@router.post("/run")
def run_manual(request: Request, db: Session = Depends(get_db)):
    user = require_super_admin(request, db)
    try:
        result = create_full_backup("manual")
    except Exception as exc:
        db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_FAILED", entity_type="Backup", entity_id=None, details=str(exc)[:1000]))
        db.commit()
        raise HTTPException(status_code=500, detail="Backup failed; check server backup logs") from exc
    db.add(AuditEvent(actor_user_id=user.id, action="BACKUP_CREATED", entity_type="Backup", entity_id=None, details=str(result)))
    db.commit()
    return result
