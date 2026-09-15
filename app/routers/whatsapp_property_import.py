"""Admin/Super Admin WhatsApp property import with a review gate."""
from __future__ import annotations

import json
import mimetypes
import secrets
import shutil
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
from app.models import AuditEvent, Developer, Project, Unit
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
ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "video/quicktime",
}


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _guard(request: Request, db: Session):
    actor = _user(request, db)
    return actor if actor and actor.role in ALLOWED_ROLES else None


def _staging_root() -> Path:
    root = Path(settings.uploads_path).resolve() / "property-import-staging"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _shell(actor, request: Request, title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | {escape(title)}</title><style>body{{font-family:Inter,Arial,sans-serif;background:#f5f7fb;color:#10213f;margin:0;padding:24px}}.wrap{{max-width:1150px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin-bottom:18px;box-shadow:0 5px 18px #0000000a}}h1{{margin:0 0 6px}}h2{{font-size:18px}}.muted{{color:#64748b;font-size:13px}}textarea{{width:100%;min-height:260px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:12px}}input,button{{font:inherit}}input[type=file]{{display:block;margin:8px 0}}.btn{{border:0;border-radius:9px;padding:10px 15px;font-weight:800;cursor:pointer;background:#2563eb;color:#fff}}.btn.green{{background:#15803d}}.btn.red{{background:#b91c1c}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.pill{{display:inline-block;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:800;background:#eff6ff;color:#1d4ed8}}pre{{white-space:pre-wrap;background:#f8fafc;border-radius:10px;padding:12px;overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><div class='wrap'><div class='card'><h1>{escape(title)}</h1><div class='muted'>Signed in as {escape(actor.username)} · {escape(actor.role)}</div></div>{body}</div></body></html>"""
    return HTMLResponse(html)


def _index_url(role: str) -> str:
    return "/super-admin/property-data/whatsapp-import" if role == "SUPER_ADMIN" else "/admin/property-data/whatsapp-import"


def _draft_payload(row: SalesPropertySubmission) -> dict:
    try:
        value = json.loads(row.data_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _render_import_page(request: Request, db: Session, actor, message: str | None = None, error: str | None = None) -> HTMLResponse:
    csrf = csrf_token(request)
    rows = db.scalars(select(SalesPropertySubmission).where(SalesPropertySubmission.status.in_(["DRAFT", "CONFLICT", "APPROVED"])).order_by(SalesPropertySubmission.id.desc()).limit(30)).all()
    action = _index_url(actor.role)
    body = ""
    if message:
        body += f"<div class='card'><b>{escape(message)}</b></div>"
    if error:
        body += f"<div class='card' style='border-color:#fecaca'><b>{escape(error)}</b></div>"
    body += f"""<div class='card'><h2>📲 Property Data Received by WhatsApp</h2><p class='muted'>Paste the complete WhatsApp message and optionally attach brochure/catalog PDFs, images and videos. The importer extracts information, checks project identity and creates a review draft. Nothing is committed to Property Data until approval.</p><form method='post' action='{action}/analyze' enctype='multipart/form-data'><input type='hidden' name='csrf_token' value='{csrf}'><label>WhatsApp message</label><textarea name='source_text' placeholder='Paste WhatsApp property details here...'></textarea><div class='grid'><div><label>Images / brochure pages</label><input type='file' name='files' multiple accept='.jpg,.jpeg,.png,.webp,.pdf'></div><div><label>Video</label><input type='file' name='files' multiple accept='.mp4,.mov'></div></div><button class='btn' type='submit'>🤖 Analyze & Create Review Draft</button></form></div>"""
    body += "<div class='card'><h2>Import review queue</h2><table><tr><th>ID</th><th>Status</th><th>Project candidates</th><th>Created</th><th>Action</th></tr>"
    for row in rows:
        data = _draft_payload(row)
        candidates = ", ".join(str(x) for x in data.get("project_candidates", [])) or "Not identified"
        action_html = f"<a class='btn' href='{action}/{row.id}'>Review</a>" if row.status in {"DRAFT", "CONFLICT"} else "Committed"
        body += f"<tr><td>#{row.id}</td><td><span class='pill'>{escape(row.status)}</span></td><td>{escape(candidates)}</td><td>{escape(str(row.created_at))}</td><td>{action_html}</td></tr>"
    if not rows:
        body += "<tr><td colspan='5' class='muted'>No imports yet.</td></tr>"
    body += "</table></div>"
    return _shell(actor, request, "WhatsApp Property Import", body)


@router.get("/admin/property-data/whatsapp-import", response_class=HTMLResponse)
def admin_import_page(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "ADMIN":
        return RedirectResponse("/", status_code=303)
    return _render_import_page(request, db, actor)


@router.get("/super-admin/property-data/whatsapp-import", response_class=HTMLResponse)
def super_admin_import_page(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/super-admin/login", status_code=303)
    return _render_import_page(request, db, actor)


async def _save_staged_files(files: list[UploadFile], draft_token: str) -> list[dict]:
    root = _staging_root() / draft_token
    root.mkdir(parents=True, exist_ok=False)
    saved = []
    try:
        for upload in files:
            if not upload.filename:
                continue
            mime = (upload.content_type or mimetypes.guess_type(upload.filename)[0] or "").lower()
            if mime not in ALLOWED_MIME:
                raise ValueError(f"Unsupported attachment type: {upload.filename}")
            data = await upload.read(MAX_ATTACHMENT_BYTES + 1)
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise ValueError(f"Attachment exceeds 30 MB: {upload.filename}")
            safe_name = Path(upload.filename).name
            target = root / f"{secrets.token_urlsafe(10)}-{safe_name}"
            target.write_bytes(data)
            text = attachment_text(safe_name, mime, data)
            record = attachment_record(safe_name, mime, data)
            record.update({"staged_path": str(target), "extracted_text": text[:120000]})
            saved.append(record)
        return saved
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


@router.post("/admin/property-data/whatsapp-import/analyze", dependencies=[Depends(require_csrf)])
async def analyze_admin_import(request: Request, source_text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    return await _analyze_import(request, source_text, files, db, required_role="ADMIN")


@router.post("/super-admin/property-data/whatsapp-import/analyze", dependencies=[Depends(require_csrf)])
async def analyze_super_admin_import(request: Request, source_text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    return await _analyze_import(request, source_text, files, db, required_role="SUPER_ADMIN")


async def _analyze_import(request: Request, source_text: str, files: list[UploadFile], db: Session, required_role: str):
    actor = _guard(request, db)
    if not actor or actor.role != required_role:
        return RedirectResponse(_index_url(required_role), status_code=303)
    if not source_text.strip() and not files:
        return RedirectResponse(_index_url(actor.role) + "?error=Paste+WhatsApp+text+or+attach+at+least+one+file", status_code=303)
    token = secrets.token_urlsafe(18)
    try:
        attachments = await _save_staged_files(files, token)
        parsed = build_draft(source_text.strip(), attachments, db)
        row = SalesPropertySubmission(token_hash=__import__("hashlib").sha256(token.encode()).hexdigest(), property_type="Projects", data_json=json.dumps(parsed, ensure_ascii=False), status="CONFLICT" if not parsed.get("safe_to_commit") else "DRAFT", created_by_id=actor.id)
        db.add(row)
        db.flush()
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_DRAFT_CREATED", entity_type="SalesPropertySubmission", entity_id=str(row.id), details=json.dumps({"project_candidates": parsed.get("project_candidates", []), "identity_conflict": parsed.get("identity_conflict", False), "attachments": [x["filename"] for x in attachments]})))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(_index_url(actor.role) + "?error=" + escape(str(exc))[:300].replace(" ", "+"), status_code=303)
    return RedirectResponse(f"{_index_url(actor.role)}/{row.id}", status_code=303)


@router.get("/admin/property-data/whatsapp-import/{submission_id}", response_class=HTMLResponse)
def admin_review_import(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "ADMIN": return RedirectResponse("/", status_code=303)
    return _review_page(submission_id, request, db, actor)


@router.get("/super-admin/property-data/whatsapp-import/{submission_id}", response_class=HTMLResponse)
def super_admin_review_import(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN": return RedirectResponse("/super-admin/login", status_code=303)
    return _review_page(submission_id, request, db, actor)


def _review_page(submission_id: int, request: Request, db: Session, actor):
    row = db.get(SalesPropertySubmission, submission_id)
    if not row:
        return RedirectResponse(_index_url(actor.role) + "?error=Import+draft+not+found", status_code=303)
    data = _draft_payload(row)
    candidates = data.get("project_candidates", [])
    match = data.get("project_match", {})
    conflict = data.get("identity_conflict", False)
    csrf = csrf_token(request)
    action = _index_url(actor.role)
    body = f"<div class='card'><h2>Draft #{row.id} · <span class='pill'>{escape(row.status)}</span></h2><p class='muted'>Project candidates: {escape(', '.join(candidates) or 'none')}</p><p class='muted'>Identity conflict: <b>{'YES' if conflict else 'NO'}</b> · Safe automatic commit: <b>{'YES' if data.get('safe_to_commit') else 'NO'}</b></p>"
    if data.get("source_identities"):
        body += "<h3>Source identities</h3><table><tr><th>Attachment</th><th>Detected project(s)</th><th>Developer(s)</th></tr>" + "".join(f"<tr><td>{escape(str(x.get('filename')))}</td><td>{escape(', '.join(x.get('projects', [])))}</td><td>{escape(', '.join(x.get('developers', [])))}</td></tr>" for x in data["source_identities"]) + "</table>"
    body += "</div>"
    body += "<div class='card'><h2>Extracted property data</h2><pre>" + escape(json.dumps({k: v for k, v in data.items() if k not in {'raw_text'}}, ensure_ascii=False, indent=2)) + "</pre></div>"
    body += f"""<div class='card'><h2>Commit review</h2><p class='muted'>The importer never merges sources when project identities conflict. If the same developer has multiple projects, exact project identity plus developer/city/RERA checks are required.</p><form method='post' action='{action}/{row.id}/commit' onsubmit="return confirm('Commit this reviewed property data into CRM?');"><input type='hidden' name='csrf_token' value='{csrf}'><label>Target project ID (optional; use only after manual verification)</label><input name='project_id' type='number' min='1'><button class='btn green' type='submit'>✅ Approve & Reflect in Property Data</button></form>"
    if actor.role == "SUPER_ADMIN":
        body += f"<form method='post' action='{action}/{row.id}/reject' style='margin-top:10px'><input type='hidden' name='csrf_token' value='{csrf}'><button class='btn red' type='submit'>Reject Draft</button></form>"
    body += "</div>"
    return _shell(actor, request, "Review WhatsApp Property Import", body)


@router.post("/admin/property-data/whatsapp-import/{submission_id}/commit", dependencies=[Depends(require_csrf)])
async def admin_commit_import(submission_id: int, request: Request, project_id: int | None = Form(None), db: Session = Depends(get_db)):
    return _commit_import(submission_id, request, project_id, db, required_role="ADMIN")


@router.post("/super-admin/property-data/whatsapp-import/{submission_id}/commit", dependencies=[Depends(require_csrf)])
async def super_admin_commit_import(submission_id: int, request: Request, project_id: int | None = Form(None), db: Session = Depends(get_db)):
    return _commit_import(submission_id, request, project_id, db, required_role="SUPER_ADMIN")


def _commit_import(submission_id: int, request: Request, project_id: int | None, db: Session, required_role: str):
    actor = _guard(request, db)
    if not actor or actor.role != required_role:
        return RedirectResponse(_index_url(required_role), status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row or row.status not in {"DRAFT", "CONFLICT"}:
        return RedirectResponse(_index_url(actor.role) + "?error=Import+draft+is+not+available+for+commit", status_code=303)
    data = _draft_payload(row)
    if data.get("identity_conflict") and actor.role != "SUPER_ADMIN":
        return RedirectResponse(f"{_index_url(actor.role)}/{row.id}?error=Project+identity+conflict+requires+Super+Admin+review", status_code=303)
    if not project_id:
        matches = data.get("project_match", {}).get("matches", [])
        if len(matches) != 1 or not matches[0].get("safe"):
            return RedirectResponse(f"{_index_url(actor.role)}/{row.id}?error=Select+and+verify+an+exact+target+project+before+commit", status_code=303)
        project_id = int(matches[0]["project_id"])
    project = db.get(Project, project_id)
    if not project:
        return RedirectResponse(f"{_index_url(actor.role)}/{row.id}?error=Target+project+not+found", status_code=303)
    conflicts = detect_field_conflicts(project, data)
    if conflicts:
        return RedirectResponse(f"{_index_url(actor.role)}/{row.id}?error=Existing+project+data+conflicts+with+imported+data", status_code=303)
    try:
        if data.get("city") and not project.city: project.city = data["city"]
        if data.get("locality") and not project.locality: project.locality = data["locality"]
        if data.get("rera") and not project.rera: project.rera = data["rera"]
        if data.get("possession_text") and not project.description:
            project.description = data["possession_text"]
        if data.get("amenities"):
            existing = []
            try: existing = json.loads(project.amenities_json or "[]")
            except (TypeError, ValueError): existing = []
            project.amenities_json = json.dumps(sorted({str(x) for x in existing + data["amenities"] if x}), ensure_ascii=False)
        configs = data.get("unit_configurations") or []
        for config in configs:
            # Configuration-only WhatsApp offers are kept as clearly marked CRM units;
            # they are never presented as confirmed flat numbers.
            key = f"CONFIG-{normalize_name(config.get('bhk'))}-{config.get('carpet_area')}"
            unit = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == key))
            if not unit:
                unit = Unit(project_id=project.id, unit_number=key)
            unit.bhk = config.get("bhk")
            unit.carpet_area = config.get("carpet_area")
            unit.price = config.get("price")
            unit.status = "CONFIGURATION"
            unit.availability = "SOURCE_STATED"
            unit.other_details = json.dumps({"source": "WHATSAPP_IMPORT", "source_line": config.get("source_line")}, ensure_ascii=False)
            db.add(unit)
        staging_root = _staging_root() / json.loads(json.dumps(data)).get("staging_token", "") if data.get("staging_token") else None
        # Attachments are moved only after successful database validation.
        for attachment in data.get("attachments", []):
            staged = Path(str(attachment.get("staged_path", ""))).resolve()
            if not staged.is_file() or staged.parent.parent != _staging_root().resolve():
                continue
            filename = f"{secrets.token_urlsafe(18)}{Path(staged).suffix.lower()}"
            destination = Path(settings.uploads_path).resolve() / "property-media" / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(destination))
            media_type = "PROPERTY_IMAGE" if attachment.get("mime_type", "").startswith("image/") else "PROPERTY_VIDEO" if attachment.get("mime_type", "").startswith("video/") else "PROPERTY_CATALOG"
            db.add(PropertyMedia(project_id=project.id, media_type=media_type, title=attachment.get("filename"), file_url=f"/media/property/{filename}", storage_key=f"property-media/{filename}", mime_type=attachment.get("mime_type"), file_size=attachment.get("size"), sort_order=0, is_shareable=True, uploaded_by_id=actor.id))
        row.status = "APPROVED"
        row.record_id = project.id
        row.reviewed_by_id = actor.id
        row.review_note = "Approved through WhatsApp property import review gate"
        from datetime import datetime, timezone
        row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_COMMITTED", entity_type="Projects", entity_id=str(project.id), details=json.dumps({"submission_id": row.id, "unit_configurations": len(configs), "attachments": len(data.get("attachments", []))})))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"{_index_url(actor.role)}/{row.id}?error=Commit+failed%3A+{escape(str(exc))[:250]}", status_code=303)
    return RedirectResponse(_index_url(actor.role) + "?message=Property+data+verified+and+reflected+in+CRM", status_code=303)


@router.post("/super-admin/property-data/whatsapp-import/{submission_id}/reject", dependencies=[Depends(require_csrf)])
def reject_import(submission_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN": return RedirectResponse("/super-admin/login", status_code=303)
    row = db.get(SalesPropertySubmission, submission_id)
    if not row: return RedirectResponse("/super-admin/property-data/whatsapp-import?error=Draft+not+found", status_code=303)
    row.status = "REJECTED"
    row.reviewed_by_id = actor.id
    from datetime import datetime, timezone
    row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(actor_user_id=actor.id, action="WHATSAPP_PROPERTY_IMPORT_REJECTED", entity_type="SalesPropertySubmission", entity_id=str(row.id), details="{}"))
    db.commit()
    return RedirectResponse("/super-admin/property-data/whatsapp-import?message=Import+draft+rejected", status_code=303)
