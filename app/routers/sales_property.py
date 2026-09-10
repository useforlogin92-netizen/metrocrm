from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import SalesPropertySubmission
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Unit
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


def _money(value, label):
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    try:
        number = Decimal(text)
    except Exception:
        raise ValueError(f"Invalid {label}: {text}")
    if number < 0:
        raise ValueError(f"{label} cannot be negative")
    return format(number, "f")


def _parse_variants(raw):
    try:
        variants = json.loads(raw or "[]")
    except (TypeError, ValueError):
        raise ValueError("Invalid BHK configuration")
    if not isinstance(variants, list) or not variants:
        raise ValueError("At least one BHK configuration is required")
    clean = []
    for item in variants:
        if not isinstance(item, dict):
            raise ValueError("Invalid BHK configuration row")
        bhk = str(item.get("bhk", "")).strip()[:50]
        area = str(item.get("carpet_area", "")).strip()
        if not bhk or not area:
            raise ValueError("Every configuration needs BHK and Carpet Area")
        try:
            area_value = Decimal(area)
        except Exception:
            raise ValueError(f"Invalid Carpet Area: {area}")
        if area_value <= 0:
            raise ValueError("Carpet Area must be greater than zero")
        fixed = format(area_value, "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        negotiable = str(item.get("negotiable", "")).strip().upper()
        if negotiable not in {"YES", "NO"}:
            raise ValueError("Negotiable must be Yes or No")
        clean.append({
            "bhk": bhk,
            "carpet_area": fixed,
            "price_per_sqft": _money(item.get("price_per_sqft"), "Rate per Sq.Ft."),
            "all_inclusive_price": _money(item.get("all_inclusive_price"), "All Inclusive / Bundle Price"),
            "negotiable": negotiable,
        })
    return clean


def _parse_parking(raw):
    try:
        values = json.loads(raw or "{}")
    except (TypeError, ValueError):
        raise ValueError("Invalid parking configuration")
    if values in (None, ""):
        return {}
    if not isinstance(values, dict):
        raise ValueError("Invalid parking configuration")
    clean = {}
    for bhk, count in values.items():
        name = str(bhk).strip()[:50]
        if not name:
            continue
        text = str(count).strip()
        if not text:
            continue
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid parking count for {name}")
        if number < 0:
            raise ValueError("Parking count cannot be negative")
        clean[name] = number
    return clean


def _configuration_unit_number(bhk: str, area: str, index: int = 0) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", f"CONFIG-{bhk}-{area}").strip("-")[:45]
    return f"{base}-{index}" if index else base


def _publish_unit_configurations(db: Session, project_id: int, data: dict):
    variants = _parse_variants(json.dumps(data.get("_unit_variants", [])))
    parking_by_bhk = _parse_parking(json.dumps(data.get("_parking_by_bhk", {})))
    existing = {u.unit_number for u in db.scalars(select(Unit).where(Unit.project_id == project_id)).all()}
    columns = {column.name: column for column in Unit.__table__.columns}
    property_fields = (
        "property_type", "facing", "furnishing", "possession", "rera",
        "availability", "status", "latitude", "longitude", "amenities_json",
        "photos_json", "floor_plan", "brochure", "description",
    )
    for variant in variants:
        unit_number = _configuration_unit_number(variant["bhk"], variant["carpet_area"])
        if unit_number in existing:
            continue
        unit = Unit(project_id=project_id, unit_number=unit_number, bhk=variant["bhk"], carpet_area=Decimal(variant["carpet_area"]))
        parking = parking_by_bhk.get(variant["bhk"])
        if parking is not None and "parking" in columns:
            unit.parking = str(parking)
        if "price_per_sqft" in columns:
            unit.price_per_sqft = Decimal(variant["price_per_sqft"])
        if "price" in columns:
            unit.price = Decimal(variant["all_inclusive_price"])
        for field in property_fields:
            if field in columns and field in data and data[field] not in (None, ""):
                setattr(unit, field, _convert_excel_value(columns[field], data[field]))
        pricing_meta = json.dumps({
            "rate_per_sqft": variant["price_per_sqft"],
            "all_inclusive_bundle_price": variant["all_inclusive_price"],
            "negotiable": variant["negotiable"],
        }, ensure_ascii=False)
        if "other_details" in columns:
            base_details = str(data.get("other_details") or "").strip()
            unit.other_details = f"{base_details}\nPricing: {pricing_meta}".strip()
        db.add(unit)
        existing.add(unit_number)


@router.get("/admin/property-data/sales-link", response_class=HTMLResponse)
def sales_link_page(request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    entity = request.query_params.get("entity", "Projects")
    if entity not in _models_map():
        entity = "Projects"
    return templates.TemplateResponse(
        "sales_property_link.html",
        {
            "request": request,
            "username": actor.username,
            "role": actor.role,
            "csrf_token": csrf_token(request),
            "entity": entity,
            "link": None,
        },
    )


@router.post("/admin/property-data/sales-link", dependencies=[Depends(require_csrf)], response_class=HTMLResponse)
def create_sales_link(request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    entity = request.query_params.get("entity", "Projects")
    if entity not in _models_map():
        entity = "Projects"
    raw_token = secrets.token_urlsafe(32)
    row = SalesPropertySubmission(token_hash=_hash_token(raw_token), property_type=entity, created_by_id=actor.id, status="DRAFT")
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor_user_id=actor.id, action="SALES_PROPERTY_LINK_CREATED", entity_type=entity, entity_id=str(row.id), details=json.dumps({"entity": entity})))
    db.commit()
    link = str(request.base_url).rstrip("/") + f"/sales/property/{raw_token}"
    return templates.TemplateResponse(
        "sales_property_link.html",
        {
            "request": request,
            "username": actor.username,
            "role": actor.role,
            "csrf_token": csrf_token(request),
            "entity": entity,
            "link": link,
        },
    )


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
    try:
        if row.property_type == "Projects":
            data["_unit_variants"] = _parse_variants(str(form.get("unit_variants", "[]")))
            data["_parking_by_bhk"] = _parse_parking(str(form.get("parking_by_bhk", "{}")))
        else:
            data.pop("_unit_variants", None)
            data.pop("_parking_by_bhk", None)
    except ValueError as exc:
        return RedirectResponse(f"/sales/property/{token}?error={escape(str(exc))}", status_code=303)
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
        if row.property_type == "Projects":
            _publish_unit_configurations(db, obj.id, data)
        row.record_id = obj.id
        row.status = "APPROVED"
        row.reviewed_by_id = actor.id
        row.review_note = "Approved and published to CRM"
        row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(AuditEvent(actor_user_id=actor.id, action="SALES_PROPERTY_APPROVED", entity_type=row.property_type, entity_id=str(obj.id), details=json.dumps({"submission_id": row.id, "published": True, "unit_configurations_published": row.property_type == "Projects"})))
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
