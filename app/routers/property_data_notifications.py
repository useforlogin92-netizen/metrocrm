from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditEvent, User

router = APIRouter(tags=["property-data"])


@router.get("/super-admin/property-data-notifications")
def property_data_notifications(request: Request, db: Session = Depends(get_db)):
    """Return recent Admin property-data activity for the Super Admin notification panel."""
    from app.main import _current_user

    actor = _current_user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    actions = {
        "PROPERTY_DATA_IMPORTED",
        "PROPERTY_RECORD_CREATED",
        "PROPERTY_RECORD_UPDATED",
        "PROPERTY_EXPORT_REQUESTED",
        "GODREJ_NEST_TEST_DATA_LOADED",
    }
    events = db.scalars(
        select(AuditEvent)
        .join(User, User.id == AuditEvent.actor_user_id)
        .where(User.role == "ADMIN", AuditEvent.action.in_(actions))
        .order_by(AuditEvent.id.desc())
        .limit(20)
    ).all()

    message_map = {
        "PROPERTY_DATA_IMPORTED": "Admin imported property data",
        "PROPERTY_RECORD_CREATED": "Admin created a property record",
        "PROPERTY_RECORD_UPDATED": "Admin updated a property record",
        "PROPERTY_EXPORT_REQUESTED": "Admin requested a property data export",
        "GODREJ_NEST_TEST_DATA_LOADED": "Admin loaded Godrej Nest test property data",
    }
    items = []
    for event in events:
        actor_user = db.get(User, event.actor_user_id) if event.actor_user_id else None
        items.append({
            "id": event.id,
            "action": event.action,
            "message": message_map.get(event.action, event.action),
            "username": actor_user.username if actor_user else "Admin",
            "created_at": event.created_at.isoformat() if event.created_at else None,
        })
    return JSONResponse({"count": len(items), "items": items})
