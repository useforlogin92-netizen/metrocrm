"""Admin/Super Admin WhatsApp property import with strict project identity review."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import secrets
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import PropertyMedia, SalesPropertySubmission
from app.config import settings
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Project, Unit
from app.services.whatsapp_property_import import (
    MAX_ATTACHMENT_BYTES,
    attachment_record,
    attachment_text,
    build_draft,
    detect_field_conflicts,
    normalize_name,
)

router = APIRouter(tags=["whatsapp-property-import"])
ALLOWED_ROLES = {"SUPER_ADMIN", "ADMIN"}
ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime"}


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _guard(request: Request, db: Session):
    actor = _user(request, db)
    return actor if actor and actor.role in ALLOWED_ROLES else None


def _root(name: str) -> Path:
    root = Path(settings.uploads_path).resolve() / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def _index(role: str) -> str:
    return "/super-admin/property-data/whatsapp-import" if role == "SUPER_ADMIN" else "/admin/property-data/whatsapp-import"


def _payload(row: SalesPropertySubmission) -> dict:
    try:
        value = json.loads(row.data_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _can_access(row: SalesPropertySubmission, actor) -> bool:
    return actor.role == "SUPER_ADMIN" or row.created_by_id == actor.id


def _shell(actor, title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | {escape(title)}</title><style>body{{font-family:Inter,Arial,sans-serif;background:#f5f7fb;color:#10213f;margin:0;padding:24px}}.wrap{{max-width:1150px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin-bottom:18px;box-shadow:0 5px 18px #0000000a}}h1{{margin:0 0 6px}}h2{{font-size:18px}}.muted{{color:#64748b;font-size:13px}}textarea{{width:100%;min-height:260px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:12px}}input,button{{font:inherit}}input[type=file]{{display:block;margin:8px 0}}.btn{{border:0;border-radius:9px;padding:10px 15px;font-weight:800;cursor:pointer;background:#2563eb;color:#fff;text-decoration:none;display:inline-block}}.green{{background:#15803d}}.red{{background:#b91c1c}}.pill{{display:inline-block;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:800;background:#eff6ff;color:#1d4ed8}}pre{{white-space:pre-wrap;background:#f8fafc;border-radius:10px;padding:12px;overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}@media(max-width:700px){{body{{padding:12px}}}}</style></head><body><div class='wrap'><div class='card'><h1>{escape(title)}</h1><div class='muted'>Signed in as {escape(actor.username)} · {escape(actor.role)}</div></div>{body}</div></body></html>""")


async def _stage(files: list[UploadFile], token: str) -> list[dict]:
    root = _root("property-import-staging") / token
    root.mkdir(parents=True, exist_ok=False)
    result = []
    try:
        for upload in files:
            if not upload.filename:
                continue
            mime = (upload.content_type or mimetypes.guess_type(upload.filename)[0] or "").lower()
            if mime not in ALLOWED_MIME:
                raise ValueError(f"Unsupported attachment type: {Path(upload.filename).name}")
            data = await upload.read(MAX_ATTACHMENT_BYTES + 1)
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise ValueError(f"Attachment exceeds 30 MB: {Path(upload.filename).name}")
            safe_name = Path(upload.filename).name
            target = root / f"{secrets.token_urlsafe(10)}-{safe_name}"
            target.write_bytes(data)
            extracted = attachment_text(safe_name, mime, data)
            meta = attachment_record(safe_name, mime, data)
            meta.update({"staged_path": str(target), "extracted_text": extracted[:120000]})
            result.append(meta)
        return result
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _queue(request: Request, db: Session, actor, message: str | None = None, error: str | None = None) -> HTMLResponse:
    action = _index(actor.role)
    csrf = csrf_token(request)
    stmt = select(SalesPropertySubmission).where(SalesPropertySubmission.status.in_(["DRAFT", "CONFLICT"]))
    if actor.role != "SUPER_ADMIN":
        stmt = stmt.where(SalesPropertySubmission.created_by_id == actor.id)
    rows = db.scalars(stmt.order_by(SalesPropertySubmission.id.desc()).limit(30)).all()
    body = ""
    if message: body += f"<div class='card'><b>{escape(message)}</b></div>"
    if error: body += f"<div class='card' style='border-color:#fecaca'><b>{escape(error)}</b></div>"
    body += f"""<div class='card'><h2>📲 Property Data Received by WhatsApp</h2><p class='muted'>Paste the complete WhatsApp property message in the blank box. Attach any available images, videos or PDF brochure/catalog from your computer. MetroCRM uses only information actually present in the WhatsApp text/attachments; missing facts remain blank.</p><form method='post' action='{action}/analyze' enctype='multipart/form-data'><input type='hidden' name='csrf_token' value='{csrf}'><label>WhatsApp text</label><textarea name='source_text' placeholder='Paste the complete WhatsApp message here...'></textarea><label>Images / PDF brochures / catalogs / videos</label><input type='file' name='files' multiple accept='.jpg,.jpeg,.png,.webp,.pdf,.mp4,.mov'><button class='btn' type='submit'>🤖 Analyze & Create Review Draft</button></form></div>"""
    body += "<div class='card'><h2>Review queue</h2><table><tr><th>ID</th><th>Status</th><th>Project candidates</th><th>Action</th></tr>"
    for row in rows:
        data = _payload(row)
        candidates = ", ".join(str(x) for x in data.get("project_candidates", [])) or "Not identified"
        body += f"<tr><td>#{row.id}</td><td><span class='pill'>{escape(row.status)}</span></td><td>{escape(candidates)}</td><td><a class='btn' href='{action}/{row.id}'>Review</a></td></tr>"
    if not rows: body += "<tr><td colspan='4' class='muted'>No pending imports.</td></tr>"
    body += "</table></div>"
    return _shell(actor, "WhatsApp Property Import", body)


@router.get("/admin/property-data/whatsapp-import", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "ADMIN": return RedirectResponse("/", status_code=303)
    return _queue(request, db, actor, request.query_params.get("message"), request.query_params.get("error"))


@router.get("/super-admin/property-data/whatsapp-import", response_class=HTMLResponse)
def super_admin_page(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN": return RedirectResponse("/super-admin/login", status_code=303)
    return _queue(request, db, actor, request.query_params.get("message"), request.query_params.get("error"))


async def _analyze(request: Request, source_text: str, files: list[UploadFile], db: Session, role: str):
    actor = _guard(request, db)
    if not actor or actor.role != role: return RedirectResponse(_index(role), status_code=303)
    if not source_text.strip() and not files: return RedirectResponse(_index(role) + "?error=Paste+WhatsApp+text+or+attach+a+file", status_code=303)
    token = secrets.token_urlsafe(18)
    try:
        attachments = await _stage(files, token)
        parsed = build_draft(source_text.strip(), attachments, db)
        parsed["attachments"] = attachments
        parsed["staging_token"] = token
        status = "CONFLICT" if not parsed.get("safe_to_commit") else "DRAFT"
        row = SalesPropertySubmission(token_hash=hashlib.sha256(token.encode()).hexdigest(), property_type="Projects", data_json=json.dumps(parsed, ensure_ascii=False), status=status, created_by_id=actor.id)
        db.add(row); db.flush()
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_DRAFT_CREATED", entity_type="SalesPropertySubmission", entity_id=str(row.id), details=json.dumps({"project_candidates": parsed.get("project_candidates", []), "identity_conflict": parsed.get("identity_conflict", False), "unattributed_sources": parsed.get("unattributed_sources", []), "attachments": [x["filename"] for x in attachments]})))
        db.commit()
    except Exception as exc:
        db.rollback(); shutil.rmtree(_root("property-import-staging") / token, ignore_errors=True)
        return RedirectResponse(_index(role) + "?error=" + escape(str(exc))[:250].replace(" ", "+"), status_code=303)
    return RedirectResponse(f"{_index(role)}/{row.id}?status=success", status_code=303)


@router.post("/admin/property-data/whatsapp-import/analyze", dependencies=[Depends(require_csrf)])
async def admin_analyze(request: Request, source_text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    return await _analyze(request, source_text, files, db, "ADMIN")


@router.post("/super-admin/property-data/whatsapp-import/analyze", dependencies=[Depends(require_csrf)])
async def super_admin_analyze(request: Request, source_text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    return await _analyze(request, source_text, files, db, "SUPER_ADMIN")


def _review(submission_id: int, request: Request, db: Session, actor) -> HTMLResponse:
    row = db.get(SalesPropertySubmission, submission_id)
    if not row or not _can_access(row, actor): return RedirectResponse(_index(actor.role) + "?error=Draft+not+found", status_code=303)
    data = _payload(row)
    action = _index(actor.role)
    csrf = csrf_token(request)
    status = request.query_params.get("status")
    review_error = request.query_params.get("error")
    identities = data.get("source_identities", [])
    identity_html = ""
    if identities:
        identity_html = "<h3>Source identity check</h3><table><tr><th>Source</th><th>Project(s)</th><th>Developer(s)</th></tr>" + "".join(f"<tr><td>{escape(str(x.get('filename')))}</td><td>{escape(', '.join(x.get('projects', [])))}</td><td>{escape(', '.join(x.get('developers', [])))}</td></tr>" for x in identities) + "</table>"
    unattributed = data.get("unattributed_sources") or []
    if unattributed:
        identity_html += "<p style='color:#b45309'><b>Attachment note:</b> " + escape(", ".join(map(str, unattributed))) + " could not independently identify a project from OCR. The pasted WhatsApp message remains the primary source; review the attachment before committing.</p>"
    match = data.get("project_match") or {}
    safe_matches = [x for x in match.get("matches", []) if x.get("safe")]
    suggested_id = safe_matches[0].get("project_id") if len(safe_matches) == 1 else ""
    status_html = ""
    if review_error:
        status_html = f"<div class='card' style='border-color:#fecaca;background:#fff7f7'><h2 style='margin:0 0 6px'>❌ Import failed</h2><div>{escape(review_error)}</div></div>"
    elif status == "success":
        status_html = f"<div class='card' style='border-color:#bbf7d0;background:#f0fdf4'><h2 style='margin:0 0 6px'>✅ Import submitted successfully</h2><div>Review draft <b>#{row.id}</b> was created. Nothing is written to the final project until you verify and commit it.</div></div>"
    elif status == "updated":
        status_html = f"<div class='card' style='border-color:#bbf7d0;background:#f0fdf4'><h2 style='margin:0 0 6px'>✅ Draft updated</h2><div>Your corrections are saved in review draft <b>#{row.id}</b>. The live Property Data record is still unchanged until verification.</div></div>"
    elif row.status == "CONFLICT":
        status_html = f"<div class='card' style='border-color:#fde68a;background:#fffbeb'><h2 style='margin:0 0 6px'>⚠️ Review required</h2><div>Multiple or conflicting project identities were detected. Check the details below before any commit.</div></div>"
    body = status_html + f"<div class='card'><h2>Draft #{row.id} · <span class='pill'>{escape(row.status)}</span></h2><p class='muted'>Detected project(s): <b>{escape(', '.join(data.get('project_candidates', [])) or 'none')}</b></p><p class='muted'>Identity conflict: <b>{'YES' if data.get('identity_conflict') else 'NO'}</b></p>{identity_html}</div>"
    body += "<div class='card'><h2>Extracted data</h2><pre>" + escape(json.dumps({k: v for k, v in data.items() if k not in {'raw_text', 'attachments'}}, ensure_ascii=False, indent=2)) + "</pre>"
    if data.get("attachments"):
        body += "<h3>Attachments</h3><ul>" + "".join(f"<li>{escape(str(x.get('filename')))} · {escape(str(x.get('mime_type')))} · {x.get('extracted_text_chars', 0)} extracted characters</li>" for x in data["attachments"]) + "</ul>"
    body += "</div>"
    blocked = bool(data.get("identity_conflict"))
    note = "Different project identities were detected; separate the sources before commit." if blocked else "MetroCRM will use only source-stated values. Missing WhatsApp facts stay blank; review before commit."

    editable = {
        "city": data.get("city", ""),
        "locality": data.get("locality", ""),
        "address": data.get("address", ""),
        "rera": data.get("rera", ""),
        "possession_text": data.get("possession_text", ""),
        "contact_phone": data.get("contact_phone", ""),
        "amenities": data.get("amenities") or [],
        "highlights": data.get("highlights") or [],
        "unit_configurations": data.get("unit_configurations") or [],
    }
    body += f"""<div class='card'><h2>✏️ Update Extracted Property Data</h2><p class='muted'>Correct extracted values here. These changes are saved to the review draft only; the live Property Data record changes only after verification.</p>
<form method='post' action='{action}/{row.id}/update' onsubmit="return confirm('Save these corrections to the review draft?');">
<input type='hidden' name='csrf_token' value='{csrf}'>
<label>City<input name='city' value='{escape(str(editable["city"]))}'></label>
<label>Locality<input name='locality' value='{escape(str(editable["locality"]))}'></label>
<label>Address<input name='address' value='{escape(str(editable["address"]))}'></label>
<label>RERA<input name='rera' value='{escape(str(editable["rera"]))}'></label>
<label>Possession<input name='possession_text' value='{escape(str(editable["possession_text"]))}'></label>
<label>Contact Phone<input name='contact_phone' value='{escape(str(editable["contact_phone"]))}'></label>
<label>Amenities<input name='amenities' value='{escape(", ".join(map(str, editable["amenities"])))}'></label>
<label>Highlights<textarea name='highlights' style='min-height:110px'>{escape("\\n".join(map(str, editable["highlights"])))}</textarea></label>
<label>BHK / Area / Price configurations (JSON)<textarea name='unit_configurations' style='min-height:150px'>{escape(json.dumps(editable["unit_configurations"], ensure_ascii=False, indent=2))}</textarea></label>
<button class='btn' type='submit' style='margin-top:12px'>💾 Save Draft Changes</button>
</form></div>"""

    body += f"""<div class='card'><h2>Verify target project</h2><p class='muted'><b>Safety rule:</b> {escape(note)}</p><form method='post' action='{action}/{row.id}/commit' onsubmit="return confirm('Commit this verified property import into the selected CRM project?');"><input type='hidden' name='csrf_token' value='{csrf}'><label>Exact target Project ID</label><input name='project_id' type='number' min='1' required value='{escape(str(suggested_id))}'><button class='btn green' type='submit'>✅ Verify & Reflect in CRM</button></form>"""
    if actor.role == "SUPER_ADMIN":
        body += f"<form method='post' action='{action}/{row.id}/reject' style='margin-top:10px'><input type='hidden' name='csrf_token' value='{csrf}'><button class='btn red' type='submit'>Reject Import</button></form>"
    body += "</div>"
    return _shell(actor, "Review WhatsApp Property Import", body)


@router.get("/admin/property-data/whatsapp-import/{submission_id}", response_class=HTMLResponse)
def admin_review(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "ADMIN": return RedirectResponse("/", status_code=303)
    return _review(submission_id, request, db, actor)


@router.get("/super-admin/property-data/whatsapp-import/{submission_id}", response_class=HTMLResponse)
def super_admin_review(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN": return RedirectResponse("/super-admin/login", status_code=303)
    return _review(submission_id, request, db, actor)


@router.post("/admin/property-data/whatsapp-import/{submission_id}/update", dependencies=[Depends(require_csrf)])
async def admin_update_draft(
    submission_id: int, request: Request,
    city: str = Form(""), locality: str = Form(""), address: str = Form(""),
    rera: str = Form(""), possession_text: str = Form(""), contact_phone: str = Form(""),
    amenities: str = Form(""), highlights: str = Form(""), unit_configurations: str = Form("[]"),
    db: Session = Depends(get_db),
):
    return _update_draft(submission_id, request, db, "ADMIN", city, locality, address, rera, possession_text, contact_phone, amenities, highlights, unit_configurations)


@router.post("/super-admin/property-data/whatsapp-import/{submission_id}/update", dependencies=[Depends(require_csrf)])
async def super_admin_update_draft(
    submission_id: int, request: Request,
    city: str = Form(""), locality: str = Form(""), address: str = Form(""),
    rera: str = Form(""), possession_text: str = Form(""), contact_phone: str = Form(""),
    amenities: str = Form(""), highlights: str = Form(""), unit_configurations: str = Form("[]"),
    db: Session = Depends(get_db),
):
    return _update_draft(submission_id, request, db, "SUPER_ADMIN", city, locality, address, rera, possession_text, contact_phone, amenities, highlights, unit_configurations)


def _update_draft(
    submission_id: int, request: Request, db: Session, role: str,
    city: str, locality: str, address: str, rera: str, possession_text: str,
    contact_phone: str, amenities: str, highlights: str, unit_configurations: str,
):
    actor = _guard(request, db)
    if not actor or actor.role != role:
        return RedirectResponse(_index(role), status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row or row.status not in {"DRAFT", "CONFLICT"} or not _can_access(row, actor):
        return RedirectResponse(_index(role) + "?error=Draft+is+not+available", status_code=303)
    data = _payload(row)
    try:
        configs = json.loads(unit_configurations or "[]")
        if not isinstance(configs, list) or any(not isinstance(item, dict) for item in configs):
            raise ValueError("Configurations must be a JSON list of objects")
        data.update({
            "city": city.strip(),
            "locality": locality.strip(),
            "address": address.strip(),
            "rera": rera.strip(),
            "possession_text": possession_text.strip(),
            "contact_phone": contact_phone.strip(),
            "amenities": [x.strip() for x in amenities.split(",") if x.strip()],
            "highlights": [x.strip() for x in highlights.splitlines() if x.strip()],
            "unit_configurations": configs,
        })
        data["manual_review_updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        data["manual_review_updated_by"] = actor.id
        row.data_json = json.dumps(data, ensure_ascii=False)
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_DRAFT_UPDATED", entity_type="SalesPropertySubmission", entity_id=str(row.id), details=json.dumps({"fields": ["city", "locality", "address", "rera", "possession_text", "contact_phone", "amenities", "highlights", "unit_configurations"]})))
        db.commit()
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        db.rollback()
        return RedirectResponse(f"{_index(role)}/{row.id}?error=Draft+update+failed%3A+{escape(str(exc))[:220]}", status_code=303)
    return RedirectResponse(f"{_index(role)}/{row.id}?status=updated", status_code=303)


@router.post("/admin/property-data/whatsapp-import/{submission_id}/commit", dependencies=[Depends(require_csrf)])
async def admin_commit(submission_id: int, request: Request, project_id: int = Form(...), db: Session = Depends(get_db)):
    return _commit(submission_id, request, project_id, db, "ADMIN")


@router.post("/super-admin/property-data/whatsapp-import/{submission_id}/commit", dependencies=[Depends(require_csrf)])
async def super_admin_commit(submission_id: int, request: Request, project_id: int = Form(...), db: Session = Depends(get_db)):
    return _commit(submission_id, request, project_id, db, "SUPER_ADMIN")


def _commit(submission_id: int, request: Request, project_id: int, db: Session, role: str):
    actor = _guard(request, db)
    if not actor or actor.role != role: return RedirectResponse(_index(role), status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row or row.status not in {"DRAFT", "CONFLICT"} or not _can_access(row, actor): return RedirectResponse(_index(role) + "?error=Draft+is+not+available", status_code=303)
    data = _payload(row)
    if data.get("identity_conflict"):
        return RedirectResponse(f"{_index(role)}/{row.id}?error=Multiple+project+identities+were+detected.+Separate+the+sources+before+importing.", status_code=303)
    candidates = data.get("project_candidates") or []
    project = db.get(Project, project_id)
    if not project: return RedirectResponse(f"{_index(role)}/{row.id}?error=Target+project+not+found", status_code=303)
    if not candidates or normalize_name(project.name) not in {normalize_name(x) for x in candidates}:
        return RedirectResponse(f"{_index(role)}/{row.id}?error=Target+project+does+not+match+the+detected+project+identity", status_code=303)
    conflicts = detect_field_conflicts(project, data)
    if conflicts:
        return RedirectResponse(f"{_index(role)}/{row.id}?error=Existing+project+data+conflicts+with+the+imported+data.+Manual+field+verification+is+required", status_code=303)
    created_destinations: list[Path] = []
    staging_root = _root("property-import-staging").resolve()
    try:
        if data.get("state") and not project.state: project.state = data["state"]
        if data.get("district") and not project.district: project.district = data["district"]
        if data.get("pincode") and not project.pincode: project.pincode = data["pincode"]
        if data.get("city") and not project.city: project.city = data["city"]
        if data.get("locality") and not project.locality: project.locality = data["locality"]
        if data.get("address") and not project.address: project.address = data["address"]
        if data.get("rera") and not project.rera: project.rera = data["rera"]
        if data.get("construction_status") and not project.construction_status: project.construction_status = data["construction_status"]
        if data.get("possession_text") and not project.description: project.description = data["possession_text"]
        description_parts = []
        if data.get("highlights"): description_parts.append("WhatsApp source highlights:\n- " + "\n- ".join(data["highlights"]))
        if data.get("map_url"): description_parts.append("WhatsApp source map: " + str(data["map_url"]))
        if data.get("website"): description_parts.append("WhatsApp source website: " + str(data["website"]))
        if data.get("parking"): description_parts.append("WhatsApp source parking: " + str(data["parking"]))
        if data.get("total_units"): description_parts.append("WhatsApp source total units: " + str(data["total_units"]))
        if description_parts and project.description:
            existing_description = str(project.description)
            additions = "\n\n".join(description_parts)
            if additions not in existing_description: project.description = existing_description + "\n\n" + additions
        elif description_parts and not project.description:
            project.description = "\n\n".join(description_parts)
        if data.get("amenities"):
            try: existing = json.loads(project.amenities_json or "[]")
            except (TypeError, ValueError): existing = []
            if not isinstance(existing, list): existing = []
            project.amenities_json = json.dumps(sorted({str(x) for x in existing + data["amenities"] if x}), ensure_ascii=False)
        developer = db.get(__import__('app.models', fromlist=['Developer']).Developer, project.developer_id)
        if developer and data.get("contact_phone") and not developer.contact:
            developer.contact = data["contact_phone"]
        for config in data.get("unit_configurations") or []:
            key = f"CONFIG-{normalize_name(config.get('bhk'))}-{config.get('carpet_area')}"
            unit = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == key))
            if not unit: unit = Unit(project_id=project.id, unit_number=key)
            unit.bhk = config.get("bhk"); unit.carpet_area = config.get("carpet_area"); unit.price = config.get("price")
            unit.status = "CONFIGURATION"; unit.availability = "SOURCE_STATED"
            if data.get("total_building_floors") and not unit.total_building_floors: unit.total_building_floors = data["total_building_floors"]
            if data.get("possession_text") and not unit.possession: unit.possession = data["possession_text"]
            unit.other_details = json.dumps({"source": "WHATSAPP_IMPORT", "source_line": config.get("source_line"), "wing": config.get("wing")}, ensure_ascii=False)
            db.add(unit)
        for attachment in data.get("attachments") or []:
            staged = Path(str(attachment.get("staged_path", ""))).resolve()
            if not staged.is_file() or staging_root not in staged.parents:
                raise ValueError(f"Staged attachment is missing or outside the import staging area: {attachment.get('filename', 'unknown')}")
            filename = f"{secrets.token_urlsafe(18)}{staged.suffix.lower()}"
            destination = _root("property-media") / filename
            shutil.copy2(str(staged), str(destination)); created_destinations.append(destination)
            mime = str(attachment.get("mime_type") or "application/octet-stream")
            media_type = "PROPERTY_IMAGE" if mime.startswith("image/") else "PROPERTY_VIDEO" if mime.startswith("video/") else "PROPERTY_CATALOG"
            db.add(PropertyMedia(project_id=project.id, media_type=media_type, title=str(attachment.get("filename") or "Imported attachment")[:255], file_url=f"/media/property/{filename}", storage_key=f"property-media/{filename}", mime_type=mime, file_size=attachment.get("size"), sort_order=0, is_shareable=True, uploaded_by_id=actor.id))
            if mime == "application/pdf" and not project.brochure:
                project.brochure = f"/media/property/{filename}"
        row.status = "APPROVED"; row.record_id = project.id; row.reviewed_by_id = actor.id; row.review_note = "Verified WhatsApp property import"; row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_COMMITTED", entity_type="Projects", entity_id=str(project.id), details=json.dumps({"submission_id": row.id, "units": len(data.get("unit_configurations") or []), "attachments": len(data.get("attachments") or []), "source_only": True})))
        db.commit()
        token = str(data.get("staging_token") or "")
        if token:
            token_root = (_root("property-import-staging") / Path(token).name).resolve()
            if staging_root in token_root.parents: shutil.rmtree(token_root, ignore_errors=True)
    except Exception as exc:
        db.rollback()
        for destination in created_destinations:
            try: destination.unlink(missing_ok=True)
            except OSError: pass
        return RedirectResponse(f"{_index(role)}/{row.id}?error=Commit+failed%3A+{escape(str(exc))[:250]}", status_code=303)
    return RedirectResponse(_index(role) + "?message=Verified+property+data+reflected+in+CRM", status_code=303)


@router.post("/super-admin/property-data/whatsapp-import/{submission_id}/reject", dependencies=[Depends(require_csrf)])
def reject_import(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN": return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row: return RedirectResponse("/super-admin/property-data/whatsapp-import?error=Draft+not+found", status_code=303)
    row.status = "REJECTED"; row.reviewed_by_id = actor.id; row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_REJECTED", entity_type="SalesPropertySubmission", entity_id=str(row.id), details="{}")); db.commit()
    token = str(_payload(row).get("staging_token") or "")
    if token:
        staging_root = _root("property-import-staging").resolve(); token_root = (_root("property-import-staging") / Path(token).name).resolve()
        if staging_root in token_root.parents: shutil.rmtree(token_root, ignore_errors=True)
    return RedirectResponse("/super-admin/property-data/whatsapp-import?message=Import+draft+rejected", status_code=303)
