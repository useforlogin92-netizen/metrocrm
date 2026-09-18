from __future__ import annotations

import json
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogShare, CatalogShareVisit, PropertyMedia, PropertySocialProfile
from app.csrf import csrf_token, require_csrf
from app.crm_plus_models import MarketingCampaign
from app.marketing_models import MarketingLandingVisit, MarketingLeadEvent
from app.database import get_db
from app.models import (
    AuditEvent,
    Booking,
    Commission,
    DataRequest,
    NearbyLocation,
    Project,
    SiteVisit,
    Token,
    Tower,
    Unit,
    User,
)

router = APIRouter(tags=["property-management", "activity-audit"])
templates = Jinja2Templates(directory="app/templates")

ACTIVITY_REQUEST_ACTION = "VIEW_ACTIVITY"
ACTIVITY_ENTITY = "AuditLog"


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _admin_actor(request: Request, db: Session) -> User | None:
    actor = _actor(request, db)
    return actor if actor and actor.role in {"ADMIN", "SUPER_ADMIN"} else None


def _activity_request(db: Session, user_id: int) -> DataRequest | None:
    return db.scalar(
        select(DataRequest)
        .where(
            DataRequest.requester_id == user_id,
            DataRequest.action == ACTIVITY_REQUEST_ACTION,
            DataRequest.entity_type == ACTIVITY_ENTITY,
            DataRequest.status.in_(["PENDING", "APPROVED"]),
        )
        .order_by(DataRequest.id.desc())
        .limit(1)
    )


def _delete_project(db: Session, project_id: int) -> tuple[Project | None, dict, str | None]:
    project = db.get(Project, project_id)
    if not project:
        return None, {}, "Property not found"

    unit_ids = list(db.scalars(select(Unit.id).where(Unit.project_id == project_id)).all())
    blocked = []
    if db.scalar(select(SiteVisit.id).where(SiteVisit.project_id == project_id).limit(1)) is not None:
        blocked.append("site visits")
    if db.scalar(select(Token.id).where(Token.project_id == project_id).limit(1)) is not None:
        blocked.append("tokens")
    if db.scalar(select(Booking.id).where(Booking.project_id == project_id).limit(1)) is not None:
        blocked.append("bookings")
    if db.scalar(select(Commission.id).where(Commission.project_id == project_id).limit(1)) is not None:
        blocked.append("commissions")
    if blocked:
        return None, {}, "Cannot delete this property because it has linked business records: " + ", ".join(blocked) + "."

    media_query = select(PropertyMedia).where(
        (PropertyMedia.project_id == project_id)
        | (PropertyMedia.unit_id.in_(unit_ids) if unit_ids else False)
    )
    media_rows = db.scalars(media_query).all()
    share_query = select(CatalogShare).where(
        (CatalogShare.project_id == project_id)
        | (CatalogShare.unit_id.in_(unit_ids) if unit_ids else False)
    )
    share_rows = db.scalars(share_query).all()
    social_rows = db.scalars(select(PropertySocialProfile).where(PropertySocialProfile.project_id == project_id)).all()
    nearby_rows = db.scalars(select(NearbyLocation).where(NearbyLocation.project_id == project_id)).all()
    unit_rows = db.scalars(select(Unit).where(Unit.project_id == project_id)).all()
    tower_rows = db.scalars(select(Tower).where(Tower.project_id == project_id)).all()

    share_ids = [row.id for row in share_rows]
    campaign_rows = (
        db.scalars(select(MarketingCampaign).where(MarketingCampaign.catalog_share_id.in_(share_ids))).all()
        if share_ids else []
    )
    campaign_ids = [row.id for row in campaign_rows]

    # Remove dependent marketing/share rows before deleting the catalog shares.
    # This keeps single-property and bulk-property deletion consistent and
    # prevents foreign-key errors when a property has been shared/campaigned.
    if campaign_ids:
        db.execute(delete(MarketingLeadEvent).where(MarketingLeadEvent.campaign_id.in_(campaign_ids)))
        db.execute(delete(MarketingLandingVisit).where(MarketingLandingVisit.campaign_id.in_(campaign_ids)))
        for row in campaign_rows:
            db.delete(row)
    if share_ids:
        db.execute(delete(CatalogShareVisit).where(CatalogShareVisit.share_id.in_(share_ids)))

    for row in media_rows:
        db.delete(row)
    for row in share_rows:
        db.delete(row)
    for row in social_rows:
        db.delete(row)
    for row in nearby_rows:
        db.delete(row)
    for row in unit_rows:
        db.delete(row)
    for row in tower_rows:
        db.delete(row)
    db.delete(project)

    counts = {
        "project": 1,
        "towers": len(tower_rows),
        "units": len(unit_rows),
        "nearby_locations": len(nearby_rows),
        "media": len(media_rows),
        "social_profiles": len(social_rows),
        "catalog_shares": len(share_rows),
        "marketing_campaigns": len(campaign_rows),
    }
    return project, counts, None


def _delete_property_response(request: Request, project_id: int, db: Session):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    project_name = None
    try:
        existing = db.get(Project, project_id)
        project_name = existing.name if existing else None
        project, counts, error = _delete_project(db, project_id)
        if error:
            db.rollback()
            return RedirectResponse(
                "/" + ("super-admin/property-data" if actor.role == "SUPER_ADMIN" else "admin/property-data")
                + "?entity=Projects&error=" + error.replace(" ", "+"),
                status_code=303,
            )
        db.add(
            AuditEvent(
                actor_user_id=actor.id,
                action="PROPERTY_DELETED",
                entity_type="Projects",
                entity_id=str(project_id),
                details=json.dumps({"project_name": project_name, **counts}, ensure_ascii=False),
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(
            "/" + ("super-admin/property-data" if actor.role == "SUPER_ADMIN" else "admin/property-data")
            + "?entity=Projects&error=Property+delete+failed%3A+" + str(exc).replace(" ", "+")[:300],
            status_code=303,
        )
    return RedirectResponse(
        "/" + ("super-admin/property-data" if actor.role == "SUPER_ADMIN" else "admin/property-data")
        + "?entity=Projects&message=Property+deleted%3A+" + escape(project_name or "record"),
        status_code=303,
    )


@router.post("/admin/property-data/projects/{project_id}/delete", dependencies=[Depends(require_csrf)])
def delete_project_as_admin(project_id: int, request: Request, db: Session = Depends(get_db)):
    return _delete_property_response(request, project_id, db)


@router.post("/super-admin/property-data/projects/{project_id}/delete", dependencies=[Depends(require_csrf)])
def delete_project_as_super_admin(project_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    return _delete_property_response(request, project_id, db)


def _activity_rows(db: Session, limit: int = 250, admin_scope: bool = False):
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    events = db.scalars(stmt).all()
    rows = []
    for event in events:
        user = db.get(User, event.actor_user_id) if event.actor_user_id else None
        if admin_scope and (not user or user.role in {"SUPER_ADMIN", "ADMIN"}):
            continue
        try:
            details = json.loads(event.details or "{}")
        except (TypeError, ValueError):
            details = {"raw": event.details or ""}
        rows.append(
            {
                "id": event.id,
                "username": user.username if user else "System",
                "role": user.role if user else "SYSTEM",
                "action": event.action,
                "entity_type": event.entity_type or "—",
                "entity_id": event.entity_id or "—",
                "details": json.dumps(details, ensure_ascii=False, sort_keys=True),
                "created_at": event.created_at,
            }
        )
    return rows


@router.get("/super-admin/activity-log", response_class=HTMLResponse)
def super_admin_activity_log(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    requests = db.scalars(
        select(DataRequest)
        .where(DataRequest.action == ACTIVITY_REQUEST_ACTION, DataRequest.entity_type == ACTIVITY_ENTITY)
        .order_by(DataRequest.id.desc())
        .limit(100)
    ).all()
    requester_ids = {row.requester_id for row in requests}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(requester_ids))).all()} if requester_ids else {}
    return templates.TemplateResponse(
        request,
        "activity_log.html",
        {
            "request": request,
            "username": actor.username,
            "role": actor.role,
            "avatar": actor.username[:1].upper(),
            "csrf_token": csrf_token(request),
            "rows": _activity_rows(db),
            "requests": requests,
            "users": users,
            "admin_access": True,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/admin/activity-log", response_class=HTMLResponse)
def admin_activity_log(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role != "ADMIN":
        return RedirectResponse("/dashboard", status_code=303)
    access = _activity_request(db, actor.id)
    approved = bool(access and access.status == "APPROVED")
    return templates.TemplateResponse(
        request,
        "activity_log.html",
        {
            "request": request,
            "username": actor.username,
            "role": actor.role,
            "avatar": actor.username[:1].upper(),
            "csrf_token": csrf_token(request),
            "rows": _activity_rows(db, admin_scope=True) if approved else [],
            "requests": [],
            "users": {},
            "admin_access": approved,
            "activity_request": access,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/activity-log/request", dependencies=[Depends(require_csrf)])
def request_activity_access(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role != "ADMIN":
        return RedirectResponse("/dashboard", status_code=303)
    existing = _activity_request(db, actor.id)
    if existing:
        return RedirectResponse("/admin/activity-log?error=Activity+access+is+already+pending+or+approved", status_code=303)
    row = DataRequest(
        requester_id=actor.id,
        action=ACTIVITY_REQUEST_ACTION,
        entity_type=ACTIVITY_ENTITY,
        filters_json=json.dumps({"scope": "non-admin-users"}),
        reason="Admin requested permission to view user activity log",
        status="PENDING",
    )
    db.add(row)
    db.flush()
    db.add(
        AuditEvent(
            actor_user_id=actor.id,
            action="ACTIVITY_ACCESS_REQUESTED",
            entity_type=ACTIVITY_ENTITY,
            entity_id=str(row.id),
            details=json.dumps({"status": "PENDING"}),
        )
    )
    db.commit()
    return RedirectResponse("/admin/activity-log?message=Activity+access+request+sent+to+Super+Admin", status_code=303)


def _decide_activity_request(request: Request, request_id: int, approve: bool, db: Session):
    actor = _actor(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(DataRequest, request_id)
    if not row or row.action != ACTIVITY_REQUEST_ACTION or row.entity_type != ACTIVITY_ENTITY or row.status != "PENDING":
        return RedirectResponse("/super-admin/activity-log?error=Invalid+activity+request", status_code=303)
    row.status = "APPROVED" if approve else "REJECTED"
    row.decided_by_id = actor.id
    row.decided_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)
    row.approval_reason = "Approved by Super Admin" if approve else "Rejected by Super Admin"
    db.add(
        AuditEvent(
            actor_user_id=actor.id,
            action="ACTIVITY_ACCESS_APPROVED" if approve else "ACTIVITY_ACCESS_REJECTED",
            entity_type=ACTIVITY_ENTITY,
            entity_id=str(row.id),
            details=json.dumps({"requester_id": row.requester_id, "status": row.status}),
        )
    )
    db.commit()
    return RedirectResponse("/super-admin/activity-log?message=Activity+access+request+updated", status_code=303)


@router.post("/super-admin/activity-log/requests/{request_id}/approve", dependencies=[Depends(require_csrf)])
def approve_activity_request(request: Request, request_id: int, db: Session = Depends(get_db)):
    return _decide_activity_request(request, request_id, True, db)


@router.post("/super-admin/activity-log/requests/{request_id}/reject", dependencies=[Depends(require_csrf)])
def reject_activity_request(request: Request, request_id: int, db: Session = Depends(get_db)):
    return _decide_activity_request(request, request_id, False, db)


@router.post("/super-admin/activity-log/requests/{request_id}/revoke", dependencies=[Depends(require_csrf)])
def revoke_activity_access(request: Request, request_id: int, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(DataRequest, request_id)
    if not row or row.action != ACTIVITY_REQUEST_ACTION or row.entity_type != ACTIVITY_ENTITY or row.status != "APPROVED":
        return RedirectResponse("/super-admin/activity-log?error=Invalid+approved+activity+request", status_code=303)
    row.status = "REVOKED"
    row.decided_by_id = actor.id
    db.add(
        AuditEvent(
            actor_user_id=actor.id,
            action="ACTIVITY_ACCESS_REVOKED",
            entity_type=ACTIVITY_ENTITY,
            entity_id=str(row.id),
            details=json.dumps({"requester_id": row.requester_id, "status": "REVOKED"}),
        )
    )
    db.commit()
    return RedirectResponse("/super-admin/activity-log?message=Activity+access+revoked", status_code=303)
