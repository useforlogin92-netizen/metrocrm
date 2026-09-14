"""Super Admin-controlled backup device registry."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS backup_devices (
    device_id VARCHAR(128) PRIMARY KEY,
    device_name VARCHAR(255) NOT NULL,
    device_path VARCHAR(1000),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    first_seen_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    approved_at TIMESTAMP,
    approved_by_id INTEGER,
    revoked_at TIMESTAMP
)
"""


def ensure_backup_devices_table(db: Session) -> None:
    db.execute(text(_CREATE_SQL))
    db.commit()


def register_device(db: Session, device_id: str, device_name: str, device_path: str = "") -> dict[str, object]:
    ensure_backup_devices_table(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    existing = db.execute(text("SELECT device_id, device_name, device_path, status FROM backup_devices WHERE device_id=:id"), {"id": device_id}).mappings().first()
    if existing:
        db.execute(text("UPDATE backup_devices SET device_name=:name, device_path=:path, last_seen_at=:now WHERE device_id=:id"), {"id": device_id, "name": device_name[:255], "path": device_path[:1000], "now": now})
        db.commit()
        return dict(db.execute(text("SELECT * FROM backup_devices WHERE device_id=:id"), {"id": device_id}).mappings().one())
    db.execute(text("INSERT INTO backup_devices (device_id, device_name, device_path, status, first_seen_at, last_seen_at) VALUES (:id,:name,:path,'PENDING',:now,:now)"), {"id": device_id[:128], "name": device_name[:255] or device_id[:255], "path": device_path[:1000], "now": now})
    db.commit()
    return dict(db.execute(text("SELECT * FROM backup_devices WHERE device_id=:id"), {"id": device_id}).mappings().one())


def list_devices(db: Session) -> list[dict[str, object]]:
    ensure_backup_devices_table(db)
    return [dict(row) for row in db.execute(text("SELECT * FROM backup_devices ORDER BY last_seen_at DESC")).mappings().all()]


def set_device_status(db: Session, device_id: str, status: str, approved_by_id: int | None = None) -> bool:
    ensure_backup_devices_table(db)
    status = status.upper()
    if status not in {"APPROVED", "REVOKED", "PENDING"}:
        raise ValueError("Invalid backup device status")
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    result = db.execute(text("UPDATE backup_devices SET status=:status, approved_at=CASE WHEN :status='APPROVED' THEN :now ELSE approved_at END, approved_by_id=CASE WHEN :status='APPROVED' THEN :by_id ELSE approved_by_id END, revoked_at=CASE WHEN :status='REVOKED' THEN :now ELSE NULL END WHERE device_id=:id"), {"status": status, "now": now, "by_id": approved_by_id, "id": device_id})
    db.commit()
    return result.rowcount == 1


def is_device_approved(db: Session, device_id: str) -> bool:
    ensure_backup_devices_table(db)
    row = db.execute(text("SELECT status FROM backup_devices WHERE device_id=:id"), {"id": device_id}).first()
    return bool(row and row[0] == "APPROVED")
