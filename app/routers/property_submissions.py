from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from cryptography.fernet import Fernet, InvalidToken

from app.csrf import csrf_token, require_csrf
from app.config import settings
from app.database import get_db
from app.models import AuditEvent, Developer, Project, Tower, Unit, User
from app.property_submission_models import PropertySubmission

router = APIRouter(tags=["property-submissions"])
templates = Jinja2Templates(directory="app/templates")

MAX_PLAN_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PLAN_VIDEO_BYTES = 50 * 1024 * 1024
MAX_SM_VISITING_CARD_BYTES = 5 * 1024 * 1024
ALLOWED_PLAN_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
ALLOWED_PLAN_VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_SM_VISITING_CARD_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}

BASE_FORM = {
    "sm_name": "", "sm_contact": "", "sm_visiting_card": "", "company_name": "", "designation": "",
    "project_name": "", "developer": "", "property_type": "Apartment", "city": "Mumbai", "locality": "",
    "address": "", "google_maps_url": "", "pincode": "", "rera_status": "Not Provided", "rera_number": "", "construction_status": "Under Construction",
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

def _token_cipher() -> Fernet:
    # Derive a stable encryption key from the server secret. The raw submission token
    # remains out of the database while Admin can still re-share the exact same URL.
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt_token(token: str) -> str:
    return _token_cipher().encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt_token(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _token_cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None



def _find_submission(db: Session, token: str) -> PropertySubmission | None:
    return db.scalar(select(PropertySubmission).where(PropertySubmission.token_hash == _token_hash(token)))


def _valid(submission: PropertySubmission) -> bool:
    return (
        not submission.revoked
        and submission.status in {"OPEN", "CORRECTION_REQUESTED"}
        and datetime.now(timezone.utc).replace(tzinfo=None) < submission.expires_at
    )


def _admin_role(actor: User | None) -> bool:
    return bool(actor and actor.role == "ADMIN")


def _super_role(actor: User | None) -> bool:
    return bool(actor and actor.role == "SUPER_ADMIN")


def _share_text(base_url: str, token: str, name: str) -> dict[str, str]:
    link = f"{base_url.rstrip('/')}/sm/property/{token}"
    return {
        "link": link,
        "whatsapp": f"Hello {name},\n\nMetro Property has shared a secure Property Details Submission link with you. Please open the link and submit the property/project information available with you.\n\nProperty Details Form:\n{link}\n\nThank you,\nMetro Property",
        "email": f"Subject: Metro Property – Property Details Submission\n\nHello {name},\n\nPlease use the secure Metro Property link below to submit the property/project details available with you.\n\n{link}\n\nYour submission will be reviewed by one authorized Metro Property Admin or Super Admin before it is added to the CRM database.\n\nRegards,\nMetro Property",
        "sms": f"Metro Property Property Details Form: {link} Please submit the property/project details available with you.",
    }


def _public_context(request: Request, submission: PropertySubmission, token: str) -> dict:
    payload = json.loads(submission.payload_json or "{}")
    if not payload.get("sm_name"):
        payload["sm_name"] = submission.recipient_name or ""
    if not payload.get("sm_contact"):
        payload["sm_contact"] = submission.recipient_mobile or ""
    return {"request": request, "submission": submission, "token": token, "payload": payload, "csrf_token": csrf_token(request)}


def _demo_submission() -> PropertySubmission:
    return PropertySubmission(id=0, token_hash="demo", created_by_id=0, recipient_name="Sample Sales Manager", recipient_mobile="+919999999999", expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1), payload_json="{}")


def _plan_magic_ok(content_type: str, data: bytes) -> bool:
    if content_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _plan_video_magic_ok(content_type: str, data: bytes) -> bool:
    if content_type in {"video/mp4", "video/quicktime"}:
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if content_type == "video/webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    return False


def _normalise_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _normalise_name(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _visiting_card_magic_ok(content_type: str, data: bytes) -> bool:
    return _plan_magic_ok(content_type, data)


async def _normalise_visiting_card(upload) -> str:
    if not isinstance(upload, UploadFile) or not upload.filename:
        return ""
    content_type = (upload.content_type or "").lower().strip()
    if content_type not in ALLOWED_SM_VISITING_CARD_CONTENT_TYPES:
        raise ValueError("SM visiting card must be a PDF, JPG, PNG or WEBP file.")
    data = await upload.read(MAX_SM_VISITING_CARD_BYTES + 1)
    if len(data) > MAX_SM_VISITING_CARD_BYTES:
        raise ValueError("SM visiting card must be 5 MB or smaller.")
    if not data or not _visiting_card_magic_ok(content_type, data):
        raise ValueError("The selected SM visiting card is invalid or does not match its file type.")
    return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"


async def _normalise_plan_uploads(files) -> list[str]:
    plans: list[str] = []
    for upload in files or []:
        if not isinstance(upload, UploadFile) or not upload.filename:
            plans.append("")
            continue
        content_type = (upload.content_type or "").lower().strip()
        if content_type not in ALLOWED_PLAN_CONTENT_TYPES:
            raise ValueError("Plan chart must be a PDF, JPG, PNG or WEBP file.")
        data = await upload.read(MAX_PLAN_UPLOAD_BYTES + 1)
        if len(data) > MAX_PLAN_UPLOAD_BYTES:
            raise ValueError("Each plan chart file must be 20 MB or smaller.")
        if not data or not _plan_magic_ok(content_type, data):
            raise ValueError("The selected plan chart file is invalid or does not match its file type.")
        plans.append(f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}")
    return plans


async def _normalise_plan_videos(files) -> list[str]:
    videos: list[str] = []
    for upload in files or []:
        if not isinstance(upload, UploadFile) or not upload.filename:
            videos.append("")
            continue
        content_type = (upload.content_type or "").lower().strip()
        if content_type not in ALLOWED_PLAN_VIDEO_CONTENT_TYPES:
            raise ValueError("Plan sample video must be an MP4, WEBM or MOV file.")
        data = await upload.read(MAX_PLAN_VIDEO_BYTES + 1)
        if len(data) > MAX_PLAN_VIDEO_BYTES:
            raise ValueError("Each plan sample video must be 50 MB or smaller.")
        if not data or not _plan_video_magic_ok(content_type, data):
            raise ValueError("The selected plan sample video is invalid or does not match its file type.")
        videos.append(f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}")
    return videos


def _normalise_configuration_details(configurations, carpet_areas, rates, bundle_prices, negotiable, inventory_statuses, available_units, towers=None, floors=None, parkings=None, custom_configurations=None, plan_charts=None, plan_videos=None, unit_numbers=None):
    values = [configurations or [], carpet_areas or [], rates or [], bundle_prices or [], negotiable or [], inventory_statuses or [], available_units or [], towers or [], floors or [], parkings or [], custom_configurations or [], plan_charts or [], plan_videos or [], unit_numbers or []]
    count = max((len(x) for x in values), default=0)
    details = []
    for i in range(count):
        selected = str(values[0][i] if i < len(values[0]) else "").strip()
        custom = str(values[10][i] if i < len(values[10]) else "").strip()
        unit_number = str(values[13][i] if i < len(values[13]) else "").strip()
        config = custom if selected == "Other" and custom else selected
        if not config and not any(str(values[j][i] if i < len(values[j]) else "").strip() for j in range(1, 14)):
            continue
        details.append({
            "configuration": config,
            "custom_configuration": custom,
            "unit_number": unit_number,
            "carpet_area": str(values[1][i] if i < len(values[1]) else "").strip(),
            "rate_per_sqft": str(values[2][i] if i < len(values[2]) else "").strip(),
            "bundle_price": str(values[3][i] if i < len(values[3]) else "").strip(),
            "negotiable": str(values[4][i] if i < len(values[4]) else "No").strip() or "No",
            "inventory_status": str(values[5][i] if i < len(values[5]) else "Available").strip() or "Available",
            "available_units": str(values[6][i] if i < len(values[6]) else "").strip(),
            "tower": str(values[7][i] if i < len(values[7]) else "").strip(),
            "floor": str(values[8][i] if i < len(values[8]) else "").strip(),
            "parking": str(values[9][i] if i < len(values[9]) else "").strip(),
            "plan_chart": str(values[11][i] if i < len(values[11]) else "").strip(),
            "plan_video": str(values[12][i] if i < len(values[12]) else "").strip(),
        })
    return details


def _preserve_existing_uploads(new_details: list[dict], old_details: list[dict]) -> list[dict]:
    for index, item in enumerate(new_details):
        if index >= len(old_details):
            continue
        old = old_details[index] or {}
        if not item.get("plan_chart") and old.get("plan_chart"):
            item["plan_chart"] = old["plan_chart"]
        if not item.get("plan_video") and old.get("plan_video"):
            item["plan_video"] = old["plan_video"]
    return new_details


@router.get("/property-submission/demo", response_class=HTMLResponse)
def demo_property_submission(request: Request):
    demo = _demo_submission()
    return templates.TemplateResponse("property_submission.html", {"request": request, "submission": demo, "token": "demo", "payload": {"sm_name": demo.recipient_name, "sm_contact": demo.recipient_mobile}, "csrf_token": csrf_token(request), "demo": True})


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
    submitted_sm_name = str(form.get("sm_name", "")).strip()
    submitted_sm_contact = str(form.get("sm_contact", "")).strip()
    if not submitted_sm_name or not submitted_sm_contact:
        return templates.TemplateResponse("property_submission.html", {**_public_context(request, submission, token), "error": "SM Name and Contact Number are required. Please re-enter and verify both details before submitting."}, status_code=422)
    if _normalise_name(submitted_sm_name) != _normalise_name(submission.recipient_name):
        return templates.TemplateResponse("property_submission.html", {**_public_context(request, submission, token), "error": "SM Name verification failed. Please enter the same name that was registered for this secure link."}, status_code=422)
    expected_phone = _normalise_phone(submission.recipient_mobile or "")
    actual_phone = _normalise_phone(submitted_sm_contact)
    if not expected_phone or expected_phone != actual_phone:
        return templates.TemplateResponse("property_submission.html", {**_public_context(request, submission, token), "error": "SM Contact Number verification failed. Please enter the same mobile/contact number that was registered for this secure link."}, status_code=422)
    configurations = form.getlist("configurations")
    try:
        plan_charts = await _normalise_plan_uploads(form.getlist("configuration_plan_chart"))
        plan_videos = await _normalise_plan_videos(form.getlist("configuration_plan_video"), form.getlist("configuration_unit_number"))
        visiting_card = await _normalise_visiting_card(form.get("sm_visiting_card"))
    except ValueError as exc:
        payload = dict(BASE_FORM)
        payload.update({k: str(v) for k, v in form.items() if k not in {"csrf_token", "configurations", "carpet_areas", "rate_per_sqft", "bundle_prices", "configuration_negotiable", "configuration_inventory_status", "configuration_available_units", "configuration_tower", "configuration_floor", "configuration_parking", "custom_configuration", "configuration_plan_chart", "configuration_plan_video", "configuration_unit_number", "sm_visiting_card", "amenities"}})
        payload["configurations"] = configurations
        payload["amenities"] = form.getlist("amenities")
        old_payload = json.loads(submission.payload_json or "{}")
        payload["sm_visiting_card"] = old_payload.get("sm_visiting_card", "")
        return templates.TemplateResponse("property_submission.html", {**_public_context(request, submission, token), "payload": payload, "error": str(exc)}, status_code=422)
    old_payload = json.loads(submission.payload_json or "{}")
    if not visiting_card:
        visiting_card = old_payload.get("sm_visiting_card", "")
    details = _normalise_configuration_details(configurations, form.getlist("carpet_areas"), form.getlist("rate_per_sqft"), form.getlist("bundle_prices"), form.getlist("configuration_negotiable"), form.getlist("configuration_inventory_status"), form.getlist("configuration_available_units"), form.getlist("configuration_tower"), form.getlist("configuration_floor"), form.getlist("configuration_parking"), form.getlist("custom_configuration"), plan_charts, plan_videos, form.getlist("configuration_unit_number"))
    required = {"project_name", "developer", "property_type", "city"}
    missing = [field for field in required if not str(form.get(field, "")).strip()]
    # Project-only submissions are valid. Configuration/unit/pricing data is added only when supplied by the SM.
    if details and any(not item.get("configuration") for item in details):
        missing.append("configuration name")
    if missing:
        payload = dict(BASE_FORM)
        payload.update({k: str(v) for k, v in form.items() if k not in {"csrf_token", "configurations", "carpet_areas", "rate_per_sqft", "bundle_prices", "configuration_negotiable", "configuration_inventory_status", "configuration_available_units", "configuration_tower", "configuration_floor", "configuration_parking", "custom_configuration", "configuration_plan_chart", "configuration_plan_video", "configuration_unit_number", "sm_visiting_card", "amenities"}})
        payload["sm_visiting_card"] = visiting_card
        payload["configurations"] = configurations
        payload["configuration_details"] = details
        payload["amenities"] = form.getlist("amenities")
        submission.payload_json = json.dumps(payload, ensure_ascii=False)
        db.commit()
        return templates.TemplateResponse("property_submission.html", {**_public_context(request, submission, token), "error": "Please select at least one configuration and complete carpet area, rate/sq.ft and bundle price for every selected configuration."}, status_code=422)
    old_details = old_payload.get("configuration_details") or []
    revision_history = old_payload.get("revision_history") or []
    if old_payload and old_details:
        revision_history.append({"submitted_at": old_payload.get("last_submitted_at"), "payload": old_payload})
        details = _preserve_existing_uploads(details, old_details)
    payload = dict(BASE_FORM)
    for key in payload:
        if key in {"configurations", "configuration_details", "amenities", "sm_visiting_card"}:
            continue
        payload[key] = str(form.get(key, "")).strip()
    payload["sm_name"] = submitted_sm_name
    payload["sm_contact"] = submitted_sm_contact
    payload["sm_visiting_card"] = visiting_card
    payload["configurations"] = configurations
    payload["configuration_details"] = details
    payload["amenities"] = form.getlist("amenities")
    if details:
        first = details[0]
        payload["starting_price"] = first.get("bundle_price", "")
        payload["price_type"] = "All Inclusive"
        payload["price_negotiable"] = first.get("negotiable", "No")
        payload["carpet_area"] = first.get("carpet_area", "")
        payload["rate_per_sqft"] = first.get("rate_per_sqft", "")
        payload["bundle_price"] = first.get("bundle_price", "")
        payload["inventory_status"] = first.get("inventory_status", "Available")
        payload["available_units"] = first.get("available_units", "")
    submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    payload["last_submitted_at"] = submitted_at.isoformat()
    payload.setdefault("first_submitted_at", submitted_at.isoformat())
    update_history = payload.get("update_history") or []
    update_history.append(
        {
            "updated_at": submitted_at.isoformat(),
            "type": "FIRST_SUBMISSION" if len(update_history) == 0 else "CORRECTION_RESUBMISSION",
            "configuration_count": len(details),
            "project_name": payload.get("project_name", ""),
        }
    )
    payload["update_history"] = update_history
    payload["revision_history"] = revision_history
    submission.payload_json = json.dumps(payload, ensure_ascii=False)
    submission.status = "SUBMITTED"
    submission.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=None, action="SM_PROPERTY_SUBMITTED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"recipient": submission.recipient_name, "configuration_count": len(details), "revision_count": len(revision_history), "google_maps_url_present": bool(payload.get("google_maps_url")), "sm_identity_verified": True, "sm_visiting_card_present": bool(visiting_card)})))
    db.commit()
    return templates.TemplateResponse("property_submission_success.html", {"request": request, "submission": submission})


@router.get("/sm/property/{token}", response_class=HTMLResponse)
def sm_property_submission_form(token: str, request: Request, db: Session = Depends(get_db)):
    """Canonical Metro Property public SM route."""
    return property_submission_form(token, request, db)


@router.post("/sm/property/{token}", dependencies=[Depends(require_csrf)])
async def sm_property_submission_submit(token: str, request: Request, db: Session = Depends(get_db)):
    """Canonical Metro Property public SM submission endpoint."""
    return await property_submission_submit(token, request, db)


def _management_page(request: Request, db: Session, actor: User, portal: str):
    rows = db.scalars(select(PropertySubmission).order_by(PropertySubmission.id.desc()).limit(100)).all()
    new_count = sum(1 for row in rows if row.status == "SUBMITTED")
    correction_count = sum(1 for row in rows if row.status == "CORRECTION_REQUESTED")
    listing_dates = {}
    for row in rows:
        listing_dates[row.id] = db.scalar(
            select(AuditEvent.created_at)
            .where(
                AuditEvent.entity_type == "PropertySubmission",
                AuditEvent.entity_id == str(row.id),
                AuditEvent.action == "SM_PROPERTY_IMPORTED",
            )
            .order_by(AuditEvent.created_at.asc())
            .limit(1)
        )
    return templates.TemplateResponse(
        "property_submissions_admin.html",
        {
            "request": request,
            "actor": actor,
            "rows": rows,
            "portal": portal,
            "new_count": new_count,
            "correction_count": correction_count,
            "listing_dates": listing_dates,
            "csrf_token": csrf_token(request),
        },
    )


@router.get("/admin/property-submissions", response_class=HTMLResponse)
def admin_property_submissions(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if _super_role(actor):
        return RedirectResponse("/super-admin/property-submissions", status_code=303)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    return _management_page(request, db, actor, "admin")


@router.get("/super-admin/property-submissions", response_class=HTMLResponse)
def super_property_submissions(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if _admin_role(actor):
        return RedirectResponse("/admin/property-submissions", status_code=303)
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
    mobile = str(form.get("recipient_mobile", "")).strip()
    if not name:
        return RedirectResponse(request.url.path + "?error=SM+name+is+required", status_code=303)
    if not mobile or len(_normalise_phone(mobile)) != 10:
        return RedirectResponse(request.url.path + "?error=Valid+10-digit+SM+contact+number+is+required", status_code=303)
    try:
        days = max(1, min(30, int(form.get("expires_days", "7") or 7)))
    except (TypeError, ValueError):
        days = 7
    token = secrets.token_urlsafe(32)
    submission = PropertySubmission(token_hash=_token_hash(token), token_encrypted=_encrypt_token(token), created_by_id=actor.id, recipient_name=name, recipient_mobile=mobile, recipient_email=str(form.get("recipient_email", "")).strip() or None, payload_json=json.dumps({"company_name":str(form.get("company_name","")).strip(),"designation":str(form.get("designation","")).strip(),"developer":str(form.get("developer","")).strip(),"project_name":str(form.get("project_name","")).strip()},ensure_ascii=False), expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days))
    db.add(submission)
    db.flush()
    db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_LINK_CREATED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"recipient": name, "expires_days": days, "contact_verified_required": True})))
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


def _import_submission(db: Session, actor: User, submission: PropertySubmission, role: str) -> None:
    payload = json.loads(submission.payload_json or "{}")
    developer_name = str(payload.get("developer", "")).strip()
    project_name = str(payload.get("project_name", "")).strip()
    developer = db.scalar(select(Developer).where(Developer.name.ilike(developer_name)).limit(1)) if developer_name else None
    if not developer:
        developer = Developer(name=developer_name, details=json.dumps({"source": "SM submission", "submission_id": submission.id}))
        db.add(developer)
        db.flush()
    project = db.scalar(
        select(Project).where(
            Project.developer_id == developer.id,
            Project.name.ilike(project_name),
            Project.city.ilike(str(payload.get("city") or "")),
            Project.locality.ilike(str(payload.get("locality") or "")),
        ).limit(1)
    )
    sm_metadata = {"sm_name": payload.get("sm_name"), "sm_contact": payload.get("sm_contact"), "sm_visiting_card": payload.get("sm_visiting_card"), "sm_submission_id": submission.id}
    if not project:
        project_description = json.dumps({"highlights": payload.get("highlights") or "", "google_maps_url": payload.get("google_maps_url") or "", "sm_name": payload.get("sm_name") or "", "sm_contact": payload.get("sm_contact") or "", "sm_visiting_card": payload.get("sm_visiting_card") or "", "sm_submission_id": submission.id}, ensure_ascii=False)
        project = Project(developer_id=developer.id, name=project_name, city=payload.get("city"), locality=payload.get("locality"), address=payload.get("address"), pincode=payload.get("pincode"), rera=payload.get("rera_number"), construction_status=payload.get("construction_status") or None, possession_date=None, amenities_json=json.dumps(payload.get("amenities", []), ensure_ascii=False), description=project_description)
        db.add(project)
        db.flush()
    details = payload.get("configuration_details") or []
    for index, item in enumerate(details, 1):
        unit_number = str(item.get("unit_number") or "").strip()
        tower_name = str(item.get("tower") or "").strip()
        tower = None
        if tower_name:
            tower = db.scalar(select(Tower).where(Tower.project_id == project.id, Tower.name.ilike(tower_name)).limit(1))
            if not tower:
                tower = Tower(project_id=project.id, name=tower_name, floors=None, possession_date=None, details=json.dumps({"source":"SM submission","submission_id":submission.id}, ensure_ascii=False))
                db.add(tower)
                db.flush()
        # A configuration without an explicit unit number is project/tower-level data only.
        # Do not manufacture a fake Unit record.
        if not unit_number:
            continue
        price = float(item["bundle_price"]) if str(item.get("bundle_price", "")).strip() else None
        carpet = float(item["carpet_area"]) if str(item.get("carpet_area", "")).strip() else None
        floor_value = str(item.get("floor", "")).strip()
        floor_number = int(floor_value) if floor_value.isdigit() else None
        existing = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == unit_number).limit(1))
        if existing:
            continue
        unit_description = {"rate_per_sqft": item.get("rate_per_sqft"), "negotiable": item.get("negotiable"), "available_units": item.get("available_units"), "tower": tower_name, "floor": item.get("floor"), "plan_video": item.get("plan_video"), **sm_metadata}
        if payload.get("google_maps_url"):
            unit_description["google_maps_url"] = payload.get("google_maps_url")
        db.add(Unit(project_id=project.id, tower_id=tower.id if tower else None, unit_number=unit_number, bhk=item.get("configuration"), property_type=payload.get("property_type"), carpet_area=carpet, built_up_area=float(payload["built_up_area"]) if payload.get("built_up_area") else None, price=price, parking=item.get("parking") or payload.get("parking"), facing=payload.get("facing"), floor=floor_number, possession=payload.get("possession_status") or None, availability=item.get("inventory_status") or "Available", status="AVAILABLE", amenities_json=json.dumps(payload.get("amenities", []), ensure_ascii=False), brochure=payload.get("brochure_url") or None, floor_plan=item.get("plan_chart") or payload.get("floor_plan_url") or None, description=json.dumps(unit_description, ensure_ascii=False), other_details=json.dumps({"sm_name": payload.get("sm_name"), "sm_contact": payload.get("sm_contact"), "sm_visiting_card": payload.get("sm_visiting_card"), "sm_submission_id": submission.id}, ensure_ascii=False)))
    submission.status = "IMPORTED"
    submission.revoked = True
    submission.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_IMPORTED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"project_id": project.id, "developer_id": developer.id, "configuration_count": len(details), "approved_by_role": role, "approved_by_user_id": actor.id, "sm_name": payload.get("sm_name"), "sm_contact": payload.get("sm_contact"), "sm_visiting_card_present": bool(payload.get("sm_visiting_card")), "link_locked": True})))


def _approve(request: Request, db: Session, actor: User, submission: PropertySubmission, role: str):
    if submission.status != "SUBMITTED" or submission.revoked:
        return
    if role == "admin":
        submission.admin_approved_by = actor.id
        submission.admin_approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        submission.super_admin_approved_by = actor.id
        submission.super_admin_approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _import_submission(db, actor, submission, role)
    db.commit()


@router.post("/admin/property-submissions/{submission_id}/approve", dependencies=[Depends(require_csrf)])
def admin_property_submission_approve(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    row = db.get(PropertySubmission, submission_id)
    if row and row.status == "SUBMITTED":
        _approve(request, db, actor, row, "admin")
    return RedirectResponse("/admin/property-submissions", status_code=303)


@router.post("/super-admin/property-submissions/{submission_id}/approve", dependencies=[Depends(require_csrf)])
def super_property_submission_approve(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(PropertySubmission, submission_id)
    if row and row.status == "SUBMITTED":
        _approve(request, db, actor, row, "super-admin")
    return RedirectResponse("/super-admin/property-submissions", status_code=303)


def _request_correction(request: Request, db: Session, actor: User, submission: PropertySubmission, role: str, reason: str, admin_updates: dict | None = None):
    if submission.status != "SUBMITTED" or submission.revoked or not reason:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = json.loads(submission.payload_json or "{}")
    if admin_updates:
        for key, value in admin_updates.items():
            if key in BASE_FORM and key not in {"sm_name", "sm_contact"} and value not in (None, ""):
                payload[key] = value
    requests = payload.get("correction_requests") or []
    requests.append({"requested_by": role, "requested_by_user_id": actor.id, "requested_at": now.isoformat(), "reason": reason, "admin_filled_fields": sorted(list(admin_updates.keys())) if admin_updates else []})
    payload["correction_requests"] = requests
    payload["latest_correction_request"] = reason
    payload["admin_filled_fields"] = sorted(list(admin_updates.keys())) if admin_updates else []
    submission.payload_json = json.dumps(payload, ensure_ascii=False)
    submission.status = "CORRECTION_REQUESTED"
    submission.admin_approved_by = None
    submission.admin_approved_at = None
    submission.super_admin_approved_by = None
    submission.super_admin_approved_at = None
    # Correction re-opens the exact same secure URL. The raw token is recovered only
    # server-side from encrypted storage; the database never stores it in plaintext.
    token = _decrypt_token(submission.token_encrypted)
    if not token:
        db.rollback()
        return None
    submission.updated_at = now
    db.add(AuditEvent(actor_user_id=actor.id, action="SM_PROPERTY_CORRECTION_REQUESTED", entity_type="PropertySubmission", entity_id=str(submission.id), details=json.dumps({"role": role, "reason": reason, "admin_filled_fields": sorted(list(admin_updates.keys())) if admin_updates else [], "same_link": True})))
    db.commit()
    return token


@router.post("/admin/property-submissions/{submission_id}/request-correction", dependencies=[Depends(require_csrf)])
async def admin_property_submission_request_correction(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _admin_role(actor):
        return RedirectResponse("/admin/login", status_code=303)
    form = await request.form()
    row = db.get(PropertySubmission, submission_id)
    if row:
        updates = {key: str(form.get(key, "")).strip() for key in ("developer","project_name","city","locality","address","pincode","rera_number","construction_status","possession_date","starting_price","rate_per_sqft","bundle_price","maintenance_charges","gst_charges","registration_charges","payment_plan","nearby","highlights","other_details") if str(form.get(key, "")).strip()}
        token = _request_correction(request, db, actor, row, "admin", str(form.get("correction_reason", "")).strip(), updates)
        if token:
            share = _share_text(str(request.base_url).rstrip("/"), token, row.recipient_name)
            return templates.TemplateResponse("property_submission_share.html", {"request": request, "actor": actor, "submission": row, **share, "correction": True, "admin_filled_fields": sorted(list(updates.keys()))})
    return RedirectResponse("/admin/property-submissions", status_code=303)


@router.post("/super-admin/property-submissions/{submission_id}/request-correction", dependencies=[Depends(require_csrf)])
async def super_property_submission_request_correction(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not _super_role(actor):
        return RedirectResponse("/super-admin/login", status_code=303)
    form = await request.form()
    row = db.get(PropertySubmission, submission_id)
    if row:
        updates = {key: str(form.get(key, "")).strip() for key in ("developer","project_name","city","locality","address","pincode","rera_number","construction_status","possession_date","starting_price","rate_per_sqft","bundle_price","maintenance_charges","gst_charges","registration_charges","payment_plan","nearby","highlights","other_details") if str(form.get(key, "")).strip()}
        token = _request_correction(request, db, actor, row, "super-admin", str(form.get("correction_reason", "")).strip(), updates)
        if token:
            share = _share_text(str(request.base_url).rstrip("/"), token, row.recipient_name)
            return templates.TemplateResponse("property_submission_share.html", {"request": request, "actor": actor, "submission": row, **share, "correction": True, "admin_filled_fields": sorted(list(updates.keys()))})
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
