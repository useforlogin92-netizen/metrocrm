from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Project, User
from app.catalog_models import PropertySocialProfile

router = APIRouter(tags=["property-social"])
templates = Jinja2Templates(directory="app/templates")
SOCIAL_FIELDS = ["facebook_url", "instagram_url", "youtube_url", "whatsapp_url", "x_url", "linkedin_url", "website_url", "google_business_url"]


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _guard(request: Request, db: Session):
    user = _user(request, db)
    return user if user and user.role in {"SUPER_ADMIN", "ADMIN"} else None


def _clean_url(value: str | None):
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Social links must be complete http/https URLs")
    return value


@router.get("/admin/property-data/social", response_class=HTMLResponse)
def social_page(request: Request, project_id: int | None = None, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/dashboard", status_code=303)
    projects = db.scalars(select(Project).order_by(Project.name.asc())).all()
    selected = db.get(Project, project_id) if project_id else (projects[0] if projects else None)
    profile = db.scalar(select(PropertySocialProfile).where(PropertySocialProfile.project_id == selected.id)) if selected else None
    return templates.TemplateResponse("property_social.html", {
        "request": request, "username": actor.username, "role": actor.role, "avatar": actor.username[:1].upper(),
        "csrf_token": csrf_token(request), "projects": projects, "selected": selected, "profile": profile,
        "message": request.query_params.get("message"), "error": request.query_params.get("error"),
        "show_user_management": True, "show_integrations": False, "show_alerts": False, "show_approvals": True,
    })


@router.post("/admin/property-data/social", dependencies=[Depends(require_csrf)])
def save_social_profile(
    request: Request,
    project_id: int = Form(...),
    brand_name: str = Form(""),
    facebook_url: str = Form(""), instagram_url: str = Form(""), youtube_url: str = Form(""),
    whatsapp_url: str = Form(""), x_url: str = Form(""), linkedin_url: str = Form(""),
    website_url: str = Form(""), google_business_url: str = Form(""), share_message: str = Form(""),
    db: Session = Depends(get_db),
):
    actor = _guard(request, db)
    project = db.get(Project, project_id)
    if not actor or not project:
        return RedirectResponse("/dashboard", status_code=303)
    try:
        values = {field: _clean_url(locals()[field]) for field in SOCIAL_FIELDS}
        profile = db.scalar(select(PropertySocialProfile).where(PropertySocialProfile.project_id == project_id))
        if profile is None:
            profile = PropertySocialProfile(project_id=project_id)
            db.add(profile)
        profile.brand_name = brand_name.strip() or "Metro Property"
        for field, value in values.items():
            setattr(profile, field, value)
        profile.share_message = share_message.strip() or None
        profile.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_SOCIAL_PROFILE_UPDATED", entity_type="Project", entity_id=str(project_id), details=json.dumps({"project": project.name})))
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"/admin/property-data/social?project_id={project_id}&error=" + str(exc).replace(" ", "+")[:300], status_code=303)
    return RedirectResponse(f"/admin/property-data/social?project_id={project_id}&message=Social+links+saved", status_code=303)
