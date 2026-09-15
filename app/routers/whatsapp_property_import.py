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
    rows = db.scalars(select(SalesPropertySubmission).where(SalesPropertySubmission.status.in_(["DRAFT", "CONFLICT"])).order_by(SalesPropertySubmission.id.desc()).limit(30)).all()
    body = ""
    if message: body += f"<div class='card'><b>{escape(message)}</b></div>"
    if error: body += f"<div class='card' style='border-color:#fecaca'><b>{escape(error)}</b></div>"
    body += f"""<div class='card'><h2>📲 Property Data Received by WhatsApp</h2><p class='muted'>Paste the WhatsApp property message and attach any brochure/catalog PDF, images or videos. The system extracts available information but keeps every import in review until the target project is verified.</p><form method='post' action='{action}/analyze' enctype='multipart/form-data'><input type='hidden' name='csrf_token' value='{csrf}'><label>WhatsApp text</label><textarea name='source_text' placeholder='Paste the complete WhatsApp message here...'></textarea><label>Images / PDF brochures / catalogs / videos</label><input type='file' name='files' multiple accept='.jpg,.jpeg,.png,.webp,.pdf,.mp4,.mov'><button class='btn' type='submit'>🤖 Analyze & Create Review Draft</button></form></div>"""
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
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_DRAFT_CREATED", entity_type="SalesPropertySubmission", entity_id=str(row.id), details=json.dumps({"project_candidates": parsed.get("project_candidates", []), "identity_conflict": parsed.get("identity_conflict", False), "attachments": [x["filename"] for x in attachments]})))
        db.commit()
    except Exception as exc:
        db.rollback(); shutil.rmtree(_root("property-import-staging") / token, ignore_errors=True)
        return RedirectResponse(_index(role) + "?error=" + escape(str(exc))[:250].replace(" ", "+"), status_code=303)
    return RedirectResponse(f"{_index(role)}/{row.id}", status_code=303)


@router.post("/admin/property-data/whatsapp-import/analyze", dependencies=[Depends(require_csrf)])
async def admin_analyze(request: Request, source_text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    return await _analyze(request, source_text, files, db, "ADMIN")


@router.post("/super-admin/property-data/whatsapp-import/analyze", dependencies=[Depends(require_csrf)])
async def super_admin_analyze(request: Request, source_text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    return await _analyze(request, source_text, files, db, "SUPER_ADMIN")


def _review(submission_id: int, request: Request, db: Session, actor) -> HTMLResponse:
    row = db.get(SalesPropertySubmission, submission_id)
    if not row: return RedirectResponse(_index(actor.role) + "?error=Draft+not+found", status_code=303)
    data = _payload(row)
    action = _index(actor.role)
    csrf = csrf_token(request)
    identities = data.get("source_identities", [])
    identity_html = ""
    if identities:
        identity_html = "<h3>Source identity check</h3><table><tr><th>Source</th><th>Project(s)</th><th>Developer(s)</th></tr>" + "".join(f"<tr><td>{escape(str(x.get('filename')))}</td><td>{escape(', '.join(x.get('projects', [])))}</td><td>{escape(', '.join(x.get('developers', [])))}</td></tr>" for x in identities) + "</table>"
    body = f"<div class='card'><h2>Draft #{row.id} · <span class='pill'>{escape(row.status)}</span></h2><p class='muted'>Detected project(s): <b>{escape(', '.join(data.get('project_candidates', [])) or 'none')}</b></p><p class='muted'>Identity conflict: <b>{'YES' if data.get('identity_conflict') else 'NO'}</b></p>{identity_html}</div>"
    body += "<div class='card'><h2>Extracted data</h2><pre>" + escape(json.dumps({k: v for k, v in data.items() if k not in {'raw_text', 'attachments'}}, ensure_ascii=False, indent=2)) + "</pre>"
    if data.get("attachments"):
        body += "<h3>Attachments</h3><ul>" + "".join(f"<li>{escape(str(x.get('filename')))} · {escape(str(x.get('mime_type')))} · {x.get('extracted_text_chars', 0)} extracted characters</li>" for x in data["attachments"]) + "</ul>"
    body += "</div>"
    body += f"""<div class='card'><h2>Verify target project</h2><p class='muted'><b>Safety rule:</b> different projects found in the supplied sources are never merged. A manual target cannot override an identity conflict.</p><form method='post' action='{action}/{row.id}/commit' onsubmit="return confirm('Commit this verified property import into the selected CRM project?');"><input type='hidden' name='csrf_token' value='{csrf}'><label>Exact target Project ID</label><input name='project_id' type='number' min='1' required><button class='btn green' type='submit'>✅ Verify & Reflect in CRM</button></form>"""
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
    if not row or row.status not in {"DRAFT", "CONFLICT"}: return RedirectResponse(_index(role) + "?error=Draft+is+not+available", status_code=303)
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
    try:
        if data.get("city") and not project.city: project.city = data["city"]
        if data.get("locality") and not project.locality: project.locality = data["locality"]
        if data.get("rera") and not project.rera: project.rera = data["rera"]
        if data.get("possession_text") and not project.description: project.description = data["possession_text"]
        if data.get("amenities"):
            try: existing = json.loads(project.amenities_json or "[]")
            except (TypeError, ValueError): existing = []
            project.amenities_json = json.dumps(sorted({str(x) for x in existing + data["amenities"] if x}), ensure_ascii=False)
        for config in data.get("unit_configurations") or []:
            key = f"CONFIG-{normalize_name(config.get('bhk'))}-{config.get('carpet_area')}"
            unit = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == key))
            if not unit: unit = Unit(project_id=project.id, unit_number=key)
            unit.bhk = config.get("bhk"); unit.carpet_area = config.get("carpet_area"); unit.price = config.get("price")
            unit.status = "CONFIGURATION"; unit.availability = "SOURCE_STATED"
            unit.other_details = json.dumps({"source": "WHATSAPP_IMPORT", "source_line": config.get("source_line")}, ensure_ascii=False)
            db.add(unit)
        for attachment in data.get("attachments") or []:
            staged = Path(str(attachment.get("staged_path", ""))).resolve()
            staging_root = _root("property-import-staging").resolve()
            if not staged.is_file() or staging_root not in staged.parents: continue
            filename = f"{secrets.token_urlsafe(18)}{staged.suffix.lower()}"
            destination = _root("property-media") / filename
            shutil.move(str(staged), str(destination))
            mime = str(attachment.get("mime_type") or "application/octet-stream")
            media_type = "PROPERTY_IMAGE" if mime.startswith("image/") else "PROPERTY_VIDEO" if mime.startswith("video/") else "PROPERTY_CATALOG"
            db.add(PropertyMedia(project_id=project.id, media_type=media_type, title=str(attachment.get("filename") or "Imported attachment")[:255], file_url=f"/media/property/{filename}", storage_key=f"property-media/{filename}", mime_type=mime, file_size=attachment.get("size"), sort_order=0, is_shareable=True, uploaded_by_id=actor.id))
        row.status = "APPROVED"; row.record_id = project.id; row.reviewed_by_id = actor.id; row.review_note = "Verified WhatsApp property import"; row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_COMMITTED", entity_type="Projects", entity_id=str(project.id), details=json.dumps({"submission_id": row.id, "units": len(data.get("unit_configurations") or []), "attachments": len(data.get("attachments") or [])})))
        db.commit()
    except Exception as exc:
        db.rollback()
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
    return RedirectResponse("/super-admin/property-data/whatsapp-import?message=Import+draft+rejected", status_code=303)
