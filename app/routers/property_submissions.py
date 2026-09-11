from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Developer, Project, Unit, User
from app.property_submission_models import PropertySubmission

router = APIRouter(tags=["property-submissions"])
templates = Jinja2Templates(directory="app/templates")

BASE_FORM = {
    "project_name": "", "developer": "", "property_type": "Apartment", "city": "Mumbai", "locality": "",
    "address": "", "pincode": "", "rera_status": "Not Provided", "rera_number": "", "construction_status": "Under Construction",
    "possession_status": "", "possession_date": "", "configuration_details": [], "configurations": [],
    "starting_price": "", "price_type": "All Inclusive", "price_negotiable": "No", "carpet_area": "",
    "rate_per_sqft": "", "bundle_price": "", "built_up_area": "", "parking": "", "facing": "", "floor": "",
    "tower": "", "amenities": [], "nearby": "", "highlights": "", "inventory_status": "Available", "available_units": "",
    "maintenance_charges": "", "gst_charges": "", "registration_charges": "", "payment_plan": "",
    "brochure_url": "", "floor_plan_url": "", "photos": "", "other_details": "",
}


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _find_submission(db: Session, token: str) -> PropertySubmission | None:
    return db.scalar(select(PropertySubmission).where(PropertySubmission.token_hash == _token_hash(token)))


def _valid(submission: PropertySubmission) -> bool:
    return not submission.revoked and submission.status not in {"SUBMITTED", "IMPORTED", "REJECTED"} and datetime.now(timezone.utc).replace(tzinfo=None) < submission.expires_at


def _admin_role(actor: User | None) -> bool:
    return bool(actor and actor.role == "ADMIN")


def _super_role(actor: User | None) -> bool:
    return bool(actor and actor.role == "SUPER_ADMIN")


def _share_text(base_url: str, token: str, name: str) -> dict[str, str]:
    link = f"{base_url.rstrip('/')}/property-submission/{token}"
    return {
        "link": link,
        "whatsapp": f"Hello {name},\n\nMetroCRM has shared a secure Property Details Submission link with you. Please open the link and submit the property/project information available with you.\n\nProperty Details Form:\n{link}\n\nThank you,\nMetroCRM",
        "email": f"Subject: MetroCRM – Property Details Submission\n\nHello {name},\n\nPlease use the secure MetroCRM link below to submit the property/project details available with you.\n\n{link}\n\nYour submission will be reviewed by MetroCRM Admin and Super Admin before it is added to the CRM database.\n\nRegards,\nMetroCRM",
        "sms": f"MetroCRM Property Details Form: {link} Please submit the property/project details available with you.",
    }


def _public_context(request: Request, submission: PropertySubmission, token: str) -> dict:
    payload = json.loads(submission.payload_json or "{}")
    return {"request": request, "submission": submission, "token": token, "payload": payload, "csrf_token": csrf_token(request)}


def _demo_submission() -> PropertySubmission:
    return PropertySubmission(id=0, token_hash="demo", created_by_id=0, recipient_name="Sample Sales Manager", expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1), payload_json="{}")


def _normalise_configuration_details(configurations, carpet_areas, rates, bundle_prices, negotiable, inventory_statuses, available_units, towers=None, floors=None, parkings=None, custom_configurations=None):
    values = [configurations or [], carpet_areas or [], rates or [], bundle_prices or [], negotiable or [], inventory_statuses or [], available_units or [], towers or [], floors or [], parkings or [], custom_configurations or []]
    count = max((len(x) for x in values), default=0)
    details = []
    for i in range(count):
        selected = str(values[0][i] if i < len(values[0]) else "").strip()
        custom = str(values[10][i] if i < len(values[10]) else "").strip()
        config = custom if selected == "Other" and custom else selected
        if not config:
            continue
        details.append({
            "configuration": config,
            "carpet_area": str(values[1][i] if i < len(values[1]) else "").strip(),
            "rate_per_sqft": str(values[2][i] if i < len(values[2]) else "").strip(),
            "bundle_price": str(values[3][i] if i < len(values[3]) else "").strip(),
            "negotiable": str(values[4][i] if i < len(values[4]) else "No").strip() or "No",
            "inventory_status": str(values[5][i] if i < len(values[5]) else "Available").strip() or "Available",
            "available_units": str(values[6][i] if i < len(values[6]) else "").strip(),
            "tower": str(values[7][i] if i < len(values[7]) else "").strip(),
            "floor": str(values[8][i] if i < len(values[8]) else "").strip(),
            "parking": str(values[9][i] if i < len(values[9]) else "").strip(),
        })
    return details


@router.get("/property-submission/demo", response_class=HTMLResponse)
def demo_property_submission(request: Request):
    demo = _demo_submission()
    return templates.TemplateResponse("property_submission.html", {"request": request, "submission": demo, "token": "demo", "payload": {}, "csrf_token": csrf_token(request), "demo": True})


@router.post("/property-submission/demo", dependencies=[Depends(require_csrf)])
async def demo_property_submission_submit(request: Request):
    await request.form()
    demo = _demo_submission()
    return templates.TemplateResponse("property_submission_success.html", {"request": request, "submission": demo, "demo": True})


@router.get("/property-submission/{token}", response_class=HTMLResponse)
def property_submission_form(token: str, request: Request, db: Session = Depends(get_db)):
    submission = _find_submission(db, token)
    if not submission or not _valid(submission):
        return templates.TemplateResponse("property_submission_expired.html", {"request": request}, status_code=410)
    return templates.TemplateResponse("property_submission.html", _public_context(request, submission, token))


@router.post("/property-submission/{token}", dependencies=[Depends(require_csrf)])
async def property_submission_submit(token: str, request: Request, db: Session = Depends(get_db)):
    submission = _find_submission(db, token)
    if not submission or not _valid(submission):
        return templates.TemplateResponse("property_submission_expired.html", {"request": request}, status_code=410)
    form = await request.form()
    configurations = form.getlist("configurations")
    details = _normalise_configuration_details(
        configurations,
        form.getlist("carpet_areas"), form.getlist("rate_per_sqft"), form.getlist("bundle_prices"),
        form.getlist("configuration_negotiable"), form.getlist("configuration_inventory_status"), form.getlist("configuration_available_units"),
        form.getlist("configuration_tower"), form.getlist("configuration_floor"), form.getlist("configuration_parking"), form.getlist("custom_configuration"),
    )
    required = {"project_name", "developer", "property_type", "city", "locality", "construction_status", "possession_status"}
    missing = [field for field in required if not str(form.get(field, "")).strip()]
    if not details:
        missing.append("configuration")
    if any(not item["carpet_area"] or not item["rate_per_sqft"] or not item["bundle_price"] for item in details):
        missing.append("configuration pricing")
    if missing:
        payload = dict(BASE_FORM)
        payload.update({k: str(v) for k, v in form.items() if k not in {"csrf_token", "configurations", "carpet_areas", "rate_per_sqft", "bundle_prices", "configuration_negotiable", "configuration_inventory_status", "configuration_available_units", "configuration_tower", "configuration_floor", "configuration_parking", "custom_configuration", "amenities"}})
        payload["configurations"] = configurations
        payload["configuration_details"] = details
        payload["amenities"] = form.getlist("amenities")
        submission.payload_json = json.dumps(payload, ensure_ascii=False)
        return templates.TemplateResponse("property_submission.html", {**_public_context(request, submission, token), "error": "Please select at least one configuration and complete carpet area, rate/sq.ft and bundle price for every selected configuration."}, status_code=422)
    payload = dict(BASE_FORM)
    for key in payload:
        if key in {"configurations", "configuration_details", "amenities"}:
            continue
        payload[key] = str(form.get(key, "")).strip()
    payload["configurations"] = configurations
    payload["configuration_details"] = details
    payload["amenities"] = form.getlist("amenities")
    first = details[0]
    payload["starting_price"] = first["bundle_price"]
    payload["price_type"] = "All Inclusive"
    payload["price_negotiable"] = first["negotiable"]
    payload["carpet_area"] = first["carpet_area"]
    payload["rate_per_sqft"] = first["rate_per_sqft"]
    payload["bundle_price"] = first["bundle_price"]
    payload["inventory_status"] = first["inventory_status"]
    payload["available_units"] = first["available_units"]
    submission.payload_json = json.dumps(payload, ensure_ascii=False)
    submission.status = "SUBMITTED"
    submission.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=None, action="SM_PROPERTY_SUBMITTED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"recipient": submission.recipient_name, "configuration_count": len(details)})))
    db.commit()
    return templates.TemplateResponse("property_submission_success.html", {"request": request, "submission": submission})


def _management_page(request: Request, db: Session, actor: User, portal: str):
    rows = db.scalars(select(PropertySubmission).order_by(PropertySubmission.id.desc()).limit(100)).all()
    return templates.TemplateResponse("property_submissions_admin.html", {"request": request, "actor": actor, "rows": rows, "portal": portal, "csrf_token": csrf_token(request)})


@router.get("/admin/property-submissions", response_class=HTMLResponse)
def admin_property_submissions(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    return _management_page(request, db, actor, "admin")


@router.get("/super-admin/property-submissions", response_class=HTMLResponse)
def super_property_submissions(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    return _management_page(request, db, actor, "super-admin")


def _create_link(request: Request, db: Session, actor: User):
    return templates.TemplateResponse("property_submission_create.html", {"request": request, "actor": actor, "csrf_token": csrf_token(request)})


@router.get("/admin/property-submissions/new", response_class=HTMLResponse)
def admin_property_submission_new(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    return _create_link(request, db, actor)


@router.get("/super-admin/property-submissions/new", response_class=HTMLResponse)
def super_property_submission_new(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    return _create_link(request, db, actor)


async def _create_submission(request: Request, db: Session, actor: User):
    form = await request.form()
    name = str(form.get("recipient_name", "")).strip()
    if not name:
        return RedirectResponse(request.url.path + "?error=SM+name+is+required", status_code=303)
    days = max(1, min(30, int(form.get("expires_days", "7") or 7)))
    token = secrets.token_urlsafe(32)
    submission = PropertySubmission(token_hash=_token_hash(token), created_by_id=actor.id, recipient_name=name, recipient_mobile=str(form.get("recipient_mobile", "")).strip() or None, recipient_email=str(form.get("recipient_email", "")).strip() or None, expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days))
    db.add(submission)
    db.flush()
    db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_LINK_CREATED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"recipient": name, "expires_days": days})))
    db.commit()
    share = _share_text(str(request.base_url).rstrip("/"), token, name)
    return templates.TemplateResponse("property_submission_share.html", {"request": request, "actor": actor, "submission": submission, **share})


@router.post("/admin/property-submissions/new", dependencies=[Depends(require_csrf)])
async def admin_property_submission_create(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    return await _create_submission(request, db, actor)


@router.post("/super-admin/property-submissions/new", dependencies=[Depends(require_csrf)])
async def super_property_submission_create(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    return await _create_submission(request, db, actor)


def _approve(request: Request, db: Session, actor: User, submission: PropertySubmission, role: str):
    if submission.status in {"IMPORTED", "REJECTED"}:
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if role == "admin":
        submission.admin_approved_by = actor.id
        submission.admin_approved_at = now
        submission.status = "ADMIN_APPROVED" if submission.super_admin_approved_by is None else "APPROVED"
    else:
        submission.super_admin_approved_by = actor.id
        submission.super_admin_approved_at = now
        submission.status = "SUPER_ADMIN_APPROVED" if submission.admin_approved_by is None else "APPROVED"
    if submission.admin_approved_by and submission.super_admin_approved_by:
        payload = json.loads(submission.payload_json or "{}")
        developer_name = payload.get("developer", "").strip()
        project_name = payload.get("project_name", "").strip()
        developer = db.scalar(select(Developer).where(Developer.name.ilike(developer_name)).limit(1)) if developer_name else None
        if not developer:
            developer = Developer(name=developer_name, details=json.dumps({"source": "SM submission", "submission_id": submission.id}))
            db.add(developer)
            db.flush()
        project = db.scalar(select(Project).where(Project.developer_id == developer.id, Project.name.ilike(project_name)).limit(1))
        if not project:
            project = Project(developer_id=developer.id, name=project_name, city=payload.get("city"), locality=payload.get("locality"), address=payload.get("address"), pincode=payload.get("pincode"), rera=payload.get("rera_number"), construction_status=payload.get("construction_status"), possession_date=None, amenities_json=json.dumps(payload.get("amenities", []), ensure_ascii=False), description=payload.get("highlights"))
            db.add(project)
            db.flush()
        details = payload.get("configuration_details") or []
        for index, item in enumerate(details, 1):
            price = float(item["bundle_price"]) if str(item.get("bundle_price", "")).strip() else None
            carpet = float(item["carpet_area"]) if str(item.get("carpet_area", "")).strip() else None
            floor_value = str(item.get("floor", "")).strip()
            floor_number = int(floor_value) if floor_value.isdigit() else None
            existing = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == f"SUB-{submission.id}-{index}").limit(1))
            if existing:
                continue
            db.add(Unit(project_id=project.id, unit_number=f"SUB-{submission.id}-{index}", bhk=item.get("configuration"), property_type=payload.get("property_type"), carpet_area=carpet, built_up_area=float(payload["built_up_area"]) if payload.get("built_up_area") else None, price=price, parking=item.get("parking") or payload.get("parking"), facing=payload.get("facing"), floor=floor_number, possession=payload.get("possession_status"), availability=item.get("inventory_status") or "Available", status="AVAILABLE", amenities_json=json.dumps(payload.get("amenities", []), ensure_ascii=False), brochure=payload.get("brochure_url") or None, floor_plan=payload.get("floor_plan_url") or None, description=json.dumps({"rate_per_sqft": item.get("rate_per_sqft"), "negotiable": item.get("negotiable"), "available_units": item.get("available_units"), "tower": item.get("tower"), "floor": item.get("floor")}, ensure_ascii=False)))
        submission.status = "IMPORTED"
        db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_IMPORTED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"project_id": project.id, "developer_id": developer.id, "configuration_count": len(details)})))
    db.commit()


@router.post("/admin/property-submissions/{submission_id}/approve", dependencies=[Depends(require_csrf)])
def admin_property_submission_approve(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    row = db.get(PropertySubmission, submission_id)
    if row and row.status not in {"IMPORTED", "REJECTED"}:
        _approve(request, db, actor, row, "admin")
    return RedirectResponse("/admin/property-submissions", status_code=303)


@router.post("/super-admin/property-submissions/{submission_id}/approve", dependencies=[Depends(require_csrf)])
def super_property_submission_approve(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(PropertySubmission, submission_id)
    if row and row.status not in {"IMPORTED", "REJECTED"}:
        _approve(request, db, actor, row, "super")
    return RedirectResponse("/super-admin/property-submissions", status_code=303)


@router.post("/admin/property-submissions/{submission_id}/revoke", dependencies=[Depends(require_csrf)])
async def admin_property_submission_revoke(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    row = db.get(PropertySubmission, submission_id)
    if row:
        row.revoked = True
        row.status = "REVOKED"
        db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_LINK_REVOKED", entity_type="PropertySubmission", entity_id=str(row.id), details="{}"))
        db.commit()
    return RedirectResponse("/admin/property-submissions", status_code=303)


@router.post("/super-admin/property-submissions/{submission_id}/revoke", dependencies=[Depends(require_csrf)])
async def super_property_submission_revoke(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(PropertySubmission, submission_id)
    if row:
        row.revoked = True
        row.status = "REVOKED"
        db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_LINK_REVOKED", entity_type="PropertySubmission", entity_id=str(row.id), details="{}"))
        db.commit()
    return RedirectResponse("/super-admin/property-submissions", status_code=303)
