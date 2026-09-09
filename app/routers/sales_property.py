from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import SalesPropertySubmission
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, User
from app.routers.data_tools import _convert_excel_value, _models

router = APIRouter(tags=["sales-property-submissions"])
templates = Jinja2Templates(directory="app/templates")
ENTITY_NAMES = ("Projects", "Towers", "Units", "NearbyLocations")


def _models_map():
    models = _models()
    return {name: models[name] for name in ENTITY_NAMES if name in models}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _actor(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _admin_actor(request: Request, db: Session):
    actor = _actor(request, db)
    return actor if actor and actor.role in {"ADMIN", "SUPER_ADMIN"} else None


def _fields(entity: str):
    model, fields = _models_map()[entity]
    return model, fields


@router.get("/admin/property-data/sales-link", response_class=HTMLResponse)
def create_sales_link_page(request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    entity = request.query_params.get("entity", "Projects")
    if entity not in _models_map():
        entity = "Projects"
    raw_token = secrets.token_urlsafe(32)
    row = SalesPropertySubmission(token_hash=_hash_token(raw_token), property_type=entity, created_by_id=actor.id, status="DRAFT")
    db.add(row)
    db.add(AuditEvent(actor_user_id=actor.id, action="SALES_PROPERTY_LINK_CREATED", entity_type=entity, entity_id=str(row.id) if row.id else None, details=json.dumps({"entity": entity})))
    db.flush()
    db.commit()
    link = str(request.base_url).rstrip("/") + f"/sales/property/{raw_token}"
    return templates.TemplateResponse("sales_property_link.html", {"request": request, "username": actor.username, "role": actor.role, "csrf_token": csrf_token(request), "entity": entity, "link": link})


@router.get("/sales/property/{token}", response_class=HTMLResponse)
def sales_property_form(request: Request, token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(SalesPropertySubmission).where(SalesPropertySubmission.token_hash == _hash_token(token)))
    if not row or row.status not in {"DRAFT", "SUBMITTED"}:
        return HTMLResponse("<h2>Property submission link is invalid, expired, or already processed.</h2>", status_code=404)
    model, fields = _fields(row.property_type)
    values = json.loads(row.data_json or "{}")
    return templates.TemplateResponse("sales_property_form.html", {"request": request, "entity": row.property_type, "fields": fields, "values": values, "submission": row, "token": token, "submitted": row.status == "SUBMITTED", "getattr": getattr})


@router.post("/sales/property/{token}")
async def save_sales_property(token: str, request: Request, db: Session = Depends(get_db)):
    row = db.scalar(select(SalesPropertySubmission).where(SalesPropertySubmission.token_hash == _hash_token(token)))
    if not row or row.status not in {"DRAFT", "SUBMITTED"}:
        return HTMLResponse("<h2>Property submission link is invalid, expired, or already processed.</h2>", status_code=404)
    form = await request.form()
    model, fields = _fields(row.property_type)
    columns = {column.name: column for column in model.__table__.columns}
    data = {}
    for field in fields:
        if field == "id" or field not in columns:
            continue
        value = str(form.get(field, "")).strip()
        if field.endswith("_json") and value:
            try:
                json.loads(value)
            except ValueError:
                return RedirectResponse(f"/sales/property/{token}?error=Invalid+JSON+in+{field}", status_code=303)
        data[field] = value
    row.submitted_by_name = str(form.get("submitted_by_name", "")).strip()[:150] or None
    row.submitted_by_mobile = str(form.get("submitted_by_mobile", "")).strip()[:30] or None
    row.submitted_by_email = str(form.get("submitted_by_email", "")).strip()[:255] or None
    row.data_json = json.dumps(data, ensure_ascii=False)
    row.status = "SUBMITTED"
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=row.created_by_id, action="SALES_PROPERTY_SUBMITTED", entity_type=row.property_type, entity_id=str(row.record_id) if row.record_id else None, details=json.dumps({"submission_id": row.id, "submitted_by": row.submitted_by_name})))
    db.commit()
    return RedirectResponse(f"/sales/property/{token}?submitted=1", status_code=303)


@router.get("/admin/property-data/sales-submissions", response_class=HTMLResponse)
def sales_property_submissions(request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    rows = db.scalars(select(SalesPropertySubmission).order_by(SalesPropertySubmission.id.desc()).limit(100)).all()
    return templates.TemplateResponse("sales_property_submissions.html", {"request": request, "username": actor.username, "role": actor.role, "csrf_token": csrf_token(request), "rows": rows})


@router.post("/admin/property-data/sales-submissions/{submission_id}/approve", dependencies=[Depends(require_csrf)])
def approve_sales_property(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row or row.status != "SUBMITTED":
        return RedirectResponse("/admin/property-data/sales-submissions", status_code=303)
    model, fields = _fields(row.property_type)
    columns = {column.name: column for column in model.__table__.columns}
    data = json.loads(row.data_json or "{}")
    try:
        raw_id = str(data.get("id", "")).strip()
        obj = db.get(model, int(raw_id)) if raw_id else model()
        if raw_id and obj is None:
            raise ValueError("Property record ID does not exist")
        for field in fields:
            if field == "id" or field not in columns:
                continue
            value = data.get(field, "")
            setattr(obj, field, _convert_excel_value(columns[field], value))
        db.add(obj)
        db.flush()
        row.record_id = obj.id
        row.status = "APPROVED"
        row.reviewed_by_id = actor.id
        row.review_note = "Approved and published to CRM"
        row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(AuditEvent(actor_user_id=actor.id, action="SALES_PROPERTY_APPROVED", entity_type=row.property_type, entity_id=str(obj.id), details=json.dumps({"submission_id": row.id, "published": True})))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/admin/property-data/sales-submissions?error={escape(str(exc))}", status_code=303)
    return RedirectResponse("/admin/property-data/sales-submissions?message=Property+approved+and+published", status_code=303)


@router.post("/admin/property-data/sales-submissions/{submission_id}/reject", dependencies=[Depends(require_csrf)])
async def reject_sales_property(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row or row.status != "SUBMITTED":
        return RedirectResponse("/admin/property-data/sales-submissions", status_code=303)
    form = await request.form()
    row.status = "REJECTED"
    row.reviewed_by_id = actor.id
    row.review_note = str(form.get("review_note", "Rejected by reviewer")).strip()[:1000]
    row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=actor.id, action="SALES_PROPERTY_REJECTED", entity_type=row.property_type, entity_id=str(row.record_id) if row.record_id else None, details=json.dumps({"submission_id": row.id, "reason": row.review_note})))
    db.commit()
    return RedirectResponse("/admin/property-data/sales-submissions?message=Submission+rejected", status_code=303)
