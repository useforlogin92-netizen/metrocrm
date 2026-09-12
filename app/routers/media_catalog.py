from __future__ import annotations

import mimetypes
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import PropertyMedia
from app.config import settings
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Project, Unit

router = APIRouter(tags=["media-catalog"])
templates = Jinja2Templates(directory="app/templates")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _guard(request: Request, db: Session):
    user = _user(request, db)
    if not user or user.role not in {"SUPER_ADMIN", "ADMIN"}:
        return None
    return user


def _media_root() -> Path:
    root = Path(settings.uploads_path).resolve() / "property-media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_ext(upload: UploadFile) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext in ALLOWED_EXT:
        return ext
    return mimetypes.guess_extension(upload.content_type or "") or ""


def _sync_photos(db: Session, project_id: int | None, unit_id: int | None) -> None:
    if unit_id:
        unit = db.get(Unit, unit_id)
        if unit:
            media = db.scalars(select(PropertyMedia).where(PropertyMedia.unit_id == unit_id).order_by(PropertyMedia.sort_order.asc(), PropertyMedia.id.asc())).all()
            unit.photos_json = __import__("json").dumps([m.file_url for m in media], ensure_ascii=False)
    if project_id:
        project = db.get(Project, project_id)
        if project:
            media = db.scalars(select(PropertyMedia).where(PropertyMedia.project_id == project_id, PropertyMedia.unit_id.is_(None)).order_by(PropertyMedia.sort_order.asc(), PropertyMedia.id.asc())).all()
            project.photos_json = __import__("json").dumps([m.file_url for m in media], ensure_ascii=False)


@router.get("/admin/media-catalog", response_class=HTMLResponse)
def media_catalog_page(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    query = (request.query_params.get("q") or "").strip()
    project_id = request.query_params.get("project_id")
    unit_id = request.query_params.get("unit_id")
    stmt = select(PropertyMedia).order_by(PropertyMedia.sort_order.asc(), PropertyMedia.id.desc())
    if query:
        stmt = stmt.where(PropertyMedia.title.ilike(f"%{query}%"))
    if project_id and project_id.isdigit():
        stmt = stmt.where(PropertyMedia.project_id == int(project_id))
    if unit_id and unit_id.isdigit():
        stmt = stmt.where(PropertyMedia.unit_id == int(unit_id))
    media = db.scalars(stmt.limit(200)).all()
    projects = db.scalars(select(Project).order_by(Project.name.asc()).limit(500)).all()
    units = db.scalars(select(Unit).order_by(Unit.unit_number.asc()).limit(1000)).all()
    return templates.TemplateResponse("media_catalog.html", {
        "request": request,
        "username": actor.username,
        "role": actor.role,
        "avatar": actor.username[:1].upper(),
        "csrf_token": csrf_token(request),
        "media": media,
        "projects": projects,
        "units": units,
        "query": query,
        "selected_project_id": int(project_id) if project_id and project_id.isdigit() else None,
        "selected_unit_id": int(unit_id) if unit_id and unit_id.isdigit() else None,
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
    })


@router.post("/admin/media-catalog/upload", dependencies=[Depends(require_csrf)])
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    project_id: int | None = Form(None),
    unit_id: int | None = Form(None),
    title: str = Form(""),
    media_type: str = Form("PROPERTY_IMAGE"),
    is_shareable: bool = Form(True),
    db: Session = Depends(get_db),
):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    mime = (file.content_type or "").lower()
    ext = _safe_ext(file)
    if mime not in ALLOWED_MIME or ext not in ALLOWED_EXT:
        return RedirectResponse("/admin/media-catalog?error=Only+JPG%2C+PNG%2C+WEBP+and+GIF+images+are+supported", status_code=303)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return RedirectResponse("/admin/media-catalog?error=Image+must+be+10MB+or+smaller", status_code=303)
    if project_id and not db.get(Project, project_id):
        return RedirectResponse("/admin/media-catalog?error=Invalid+project", status_code=303)
    if unit_id and not db.get(Unit, unit_id):
        return RedirectResponse("/admin/media-catalog?error=Invalid+unit", status_code=303)
    if unit_id:
        unit = db.get(Unit, unit_id)
        if unit and project_id and unit.project_id != project_id:
            return RedirectResponse("/admin/media-catalog?error=Unit+does+not+belong+to+selected+project", status_code=303)
        if unit:
            project_id = unit.project_id
    filename = f"{secrets.token_urlsafe(18)}{ext}"
    path = _media_root() / filename
    path.write_bytes(data)
    media = PropertyMedia(
        project_id=project_id,
        unit_id=unit_id,
        media_type=(media_type or "PROPERTY_IMAGE")[:30],
        title=(title or file.filename or "Property image")[:255],
        file_url=f"/media/property/{filename}",
        storage_key=f"property-media/{filename}",
        mime_type=mime,
        file_size=len(data),
        sort_order=0,
        is_shareable=bool(is_shareable),
        uploaded_by_id=actor.id,
    )
    db.add(media)
    db.flush()
    _sync_photos(db, project_id, unit_id)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_MEDIA_UPLOADED", entity_type="PropertyMedia", entity_id=str(media.id), details=f'{{"project_id":{project_id},"unit_id":{unit_id},"shareable":{bool(is_shareable)}}}'))
    db.commit()
    return RedirectResponse("/admin/media-catalog?message=Image+uploaded+to+catalog", status_code=303)


@router.post("/admin/media-catalog/url", dependencies=[Depends(require_csrf)])
def add_media_url(
    request: Request,
    file_url: str = Form(...),
    project_id: int | None = Form(None),
    unit_id: int | None = Form(None),
    title: str = Form(""),
    media_type: str = Form("PROPERTY_IMAGE"),
    is_shareable: bool = Form(True),
    db: Session = Depends(get_db),
):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    url = file_url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        return RedirectResponse("/admin/media-catalog?error=Image+URL+must+start+with+http%3A%2F%2F+or+https%3A%2F%2F", status_code=303)
    if len(url) > 1000:
        return RedirectResponse("/admin/media-catalog?error=Image+URL+is+too+long", status_code=303)
    if unit_id:
        unit = db.get(Unit, unit_id)
        if not unit:
            return RedirectResponse("/admin/media-catalog?error=Invalid+unit", status_code=303)
        if project_id and unit.project_id != project_id:
            return RedirectResponse("/admin/media-catalog?error=Unit+does+not+belong+to+selected+project", status_code=303)
        project_id = unit.project_id
    if project_id and not db.get(Project, project_id):
        return RedirectResponse("/admin/media-catalog?error=Invalid+project", status_code=303)
    media = PropertyMedia(project_id=project_id, unit_id=unit_id, media_type=(media_type or "PROPERTY_IMAGE")[:30], title=(title or "Catalog image")[:255], file_url=url, storage_key=None, mime_type=None, file_size=None, sort_order=0, is_shareable=bool(is_shareable), uploaded_by_id=actor.id)
    db.add(media)
    db.flush()
    _sync_photos(db, project_id, unit_id)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_MEDIA_URL_ADDED", entity_type="PropertyMedia", entity_id=str(media.id), details=f'{{"project_id":{project_id},"unit_id":{unit_id},"shareable":{bool(is_shareable)}}}'))
    db.commit()
    return RedirectResponse("/admin/media-catalog?message=Catalog+image+added", status_code=303)


@router.post("/admin/media-catalog/attach", dependencies=[Depends(require_csrf)])
def attach_media(request: Request, media_ids: str = Form(""), project_id: int | None = Form(None), unit_id: int | None = Form(None), db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    ids = {int(x) for x in media_ids.split(",") if x.strip().isdigit()}
    if not ids or not (project_id or unit_id):
        return RedirectResponse("/admin/media-catalog?error=Select+images+and+a+project+or+unit", status_code=303)
    if unit_id:
        unit = db.get(Unit, unit_id)
        if not unit:
            return RedirectResponse("/admin/media-catalog?error=Invalid+unit", status_code=303)
        if project_id and unit.project_id != project_id:
            return RedirectResponse("/admin/media-catalog?error=Unit+does+not+belong+to+selected+project", status_code=303)
        project_id = unit.project_id
    rows = db.scalars(select(PropertyMedia).where(PropertyMedia.id.in_(ids))).all()
    for media in rows:
        media.project_id = project_id
        media.unit_id = unit_id
    _sync_photos(db, project_id, unit_id)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_MEDIA_ATTACHED", entity_type="PropertyMedia", entity_id=','.join(str(x.id) for x in rows), details=f'{{"project_id":{project_id},"unit_id":{unit_id}}}'))
    db.commit()
    return RedirectResponse("/admin/media-catalog?message=Selected+images+attached+to+property", status_code=303)


@router.post("/admin/media-catalog/main", dependencies=[Depends(require_csrf)])
def set_main_media(request: Request, media_id: int = Form(...), db: Session = Depends(get_db)):
    actor = _guard(request, db)
    media = db.get(PropertyMedia, media_id)
    if not actor or not media:
        return RedirectResponse("/admin/media-catalog?error=Media+not+found", status_code=404)
    siblings = db.scalars(select(PropertyMedia).where(PropertyMedia.project_id == media.project_id, PropertyMedia.unit_id == media.unit_id).order_by(PropertyMedia.id.asc())).all()
    media.sort_order = 0
    next_order = 1
    for row in siblings:
        if row.id != media.id:
            row.sort_order = next_order
            next_order += 1
    _sync_photos(db, media.project_id, media.unit_id)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_MEDIA_MAIN_CHANGED", entity_type="PropertyMedia", entity_id=str(media.id), details="{}"))
    db.commit()
    return RedirectResponse("/admin/media-catalog?message=Main+image+updated", status_code=303)


@router.post("/admin/media-catalog/shareable", dependencies=[Depends(require_csrf)])
def set_shareable(request: Request, media_id: int = Form(...), shareable: bool = Form(True), db: Session = Depends(get_db)):
    actor = _guard(request, db)
    media = db.get(PropertyMedia, media_id)
    if not actor or not media:
        return RedirectResponse("/admin/media-catalog?error=Media+not+found", status_code=404)
    media.is_shareable = bool(shareable)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_MEDIA_SHAREABILITY_CHANGED", entity_type="PropertyMedia", entity_id=str(media.id), details=f'{{"shareable":{bool(shareable)}}}'))
    db.commit()
    return RedirectResponse("/admin/media-catalog?message=Client+sharing+setting+updated", status_code=303)


@router.get("/media/property/{filename}")
def serve_property_media(filename: str, request: Request, db: Session = Depends(get_db)):
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        return HTMLResponse("Not found", status_code=404)
    media = db.scalar(select(PropertyMedia).where(PropertyMedia.storage_key == f"property-media/{filename}"))
    if not media:
        return HTMLResponse("Not found", status_code=404)
    if not media.is_shareable:
        actor = _user(request, db)
        if not actor:
            return HTMLResponse("Forbidden", status_code=403)
    path = _media_root() / filename
    if not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path, media_type=media.mime_type or "application/octet-stream", filename=filename)
