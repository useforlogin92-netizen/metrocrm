"""Admin-managed white-label settings, kept separate from login and public pages."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO
import re

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.csrf import csrf_token, require_csrf
from app.database import Base, get_db

router = APIRouter(prefix="/admin/branding", tags=["branding-settings"])
MAX_LOGO_BYTES = 2 * 1024 * 1024
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingSettings(Base):
    """Single-tenant branding and message-template settings for this CRM instance."""
    __tablename__ = "branding_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String(160), default="MetroCRM")
    project_name: Mapped[str] = mapped_column(String(160), default="Real Estate")
    primary_color: Mapped[str] = mapped_column(String(7), default="#1d4ed8")
    secondary_color: Mapped[str] = mapped_column(String(7), default="#0f172a")
    logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(40), nullable=True)
    whatsapp_template: Mapped[str] = mapped_column(Text, default="Hello {{Customer_Name}}, {{Agent_Name}} from {{Company_Name}} is contacting you about {{Project_Name}}.")
    sms_template: Mapped[str] = mapped_column(Text, default="Hello {{Customer_Name}}, {{Agent_Name}} from {{Company_Name}} will contact you about {{Project_Name}}.")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


PLACEHOLDER_RE = re.compile(r"\\{\\{([A-Za-z_][A-Za-z0-9_]*)\\}\\}")


def render_message_template(template: str, values: dict[str, str]) -> str:
    """Replace known white-label placeholders while leaving unknown ones visible."""
    return PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), template)

def _actor(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _validated_logo(raw: bytes) -> bytes:
    if not raw or len(raw) > MAX_LOGO_BYTES:
        raise ValueError("Logo must be a non-empty image no larger than 2 MB.")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Use a PNG, JPEG, or WebP logo.")
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
            if image.width > 2400 or image.height > 1200:
                raise ValueError("Logo dimensions must be at most 2400 × 1200 pixels.")
            output = BytesIO()
            if "A" in image.getbands():
                cleaned = image.convert("RGBA")
            else:
                cleaned = image.convert("RGB")
            cleaned.save(output, format="PNG", optimize=True)
            result = output.getvalue()
            if len(result) > MAX_LOGO_BYTES:
                raise ValueError("Optimized logo exceeds the 2 MB limit.")
            return result
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Uploaded file is not a valid supported image.") from exc


def _page(settings: BrandingSettings, request: Request, message: str = "") -> str:
    logo = "<p class=muted>No logo uploaded</p>"
    if settings.logo_data:
        logo = "<img class=logo src=/admin/branding/logo alt=Company-logo>"
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Branding Settings</title><style>:root{{--primary:{escape(settings.primary_color)};--secondary:{escape(settings.secondary_color)}}}
body{{font:14px Arial,sans-serif;background:#f4f7fb;color:var(--secondary);padding:22px}}main{{max-width:900px;margin:auto}}section{{background:white;padding:22px;border:1px solid #dbe4ef;border-radius:14px;margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}label{{display:block;font-weight:700;margin:10px 0 5px}}input,textarea{{box-sizing:border-box;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px}}textarea{{min-height:100px}}button{{background:var(--primary);color:white;border:0;border-radius:8px;padding:11px 16px;font-weight:700}}.logo{{max-width:240px;max-height:120px;object-fit:contain}}.muted{{color:#64748b}}.notice{{color:#166534}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><main>
<section><h1>White-label Branding</h1><p>These settings are stored for this CRM instance. They do not change the login page or public homepage.</p><p class=notice>{escape(message)}</p>{logo}
<form method=post action=/admin/branding enctype=multipart/form-data><input type=hidden name=csrf_token value="{escape(csrf_token(request))}">
<div class=grid><div><label>Company name</label><input name=company_name maxlength=160 required value="{escape(settings.company_name)}"></div>
<div><label>Project / brand label</label><input name=project_name maxlength=160 required value="{escape(settings.project_name)}"></div>
<div><label>Primary colour</label><input name=primary_color pattern="#[0-9a-fA-F]{{6}}" required value="{escape(settings.primary_color)}"></div>
<div><label>Secondary colour</label><input name=secondary_color pattern="#[0-9a-fA-F]{{6}}" required value="{escape(settings.secondary_color)}"></div></div>
<label>Upload logo (PNG, JPEG, WebP; max 2 MB)</label><input type=file name=logo accept=image/png,image/jpeg,image/webp>
<label>WhatsApp template</label><textarea name=whatsapp_template maxlength=4000 required>{escape(settings.whatsapp_template)}</textarea>
<label>SMS template</label><textarea name=sms_template maxlength=1600 required>{escape(settings.sms_template)}</textarea>
<p class=muted>Supported placeholders: {{{{Company_Name}}}}, {{{{Project_Name}}}}, {{{{Agent_Name}}}}, {{{{Customer_Name}}}}.</p><button type=submit>Save branding settings</button></form></section></main></body></html>"""


@router.get("", response_class=HTMLResponse)
def branding_settings_page(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in {"ADMIN", "SUPER_ADMIN"}:
        return RedirectResponse("/", status_code=303)
    settings = db.get(BrandingSettings, 1) or BrandingSettings(id=1, company_name="MetroCRM", project_name="Real Estate", primary_color="#1d4ed8", secondary_color="#0f172a", whatsapp_template="Hello {{Customer_Name}}, {{Agent_Name}} from {{Company_Name}} is contacting you about {{Project_Name}}.", sms_template="Hello {{Customer_Name}}, {{Agent_Name}} from {{Company_Name}} will contact you about {{Project_Name}}.")
    return HTMLResponse(_page(settings, request))


@router.get("/logo", include_in_schema=False)
def branding_logo(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in {"ADMIN", "SUPER_ADMIN"}:
        return Response(status_code=404)
    settings = db.get(BrandingSettings, 1)
    if not settings or not settings.logo_data:
        return Response(status_code=404)
    return Response(settings.logo_data, media_type=settings.logo_mime or "image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("", dependencies=[Depends(require_csrf)], response_class=HTMLResponse)
def save_branding_settings(
    request: Request,
    company_name: str = Form(..., min_length=1, max_length=160),
    project_name: str = Form(..., min_length=1, max_length=160),
    primary_color: str = Form(...),
    secondary_color: str = Form(...),
    whatsapp_template: str = Form(..., max_length=4000),
    sms_template: str = Form(..., max_length=1600),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    if not actor or actor.role not in {"ADMIN", "SUPER_ADMIN"}:
        return RedirectResponse("/", status_code=303)
    company_name = company_name.strip()
    project_name = project_name.strip()
    if not company_name or not project_name:
        return HTMLResponse("Company and project names are required.", status_code=422)
    if not COLOR_RE.fullmatch(primary_color) or not COLOR_RE.fullmatch(secondary_color):
        return HTMLResponse("Colours must be six-digit hex values such as #1d4ed8.", status_code=422)
    current = db.get(BrandingSettings, 1)
    if current is None:
        current = BrandingSettings(id=1)
        db.add(current)
    current.company_name = company_name
    current.project_name = project_name
    current.primary_color = primary_color.lower()
    current.secondary_color = secondary_color.lower()
    current.whatsapp_template = whatsapp_template.strip()
    current.sms_template = sms_template.strip()
    if logo and logo.filename:
        if logo.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            return HTMLResponse("Use a PNG, JPEG, or WebP logo.", status_code=422)
        raw = logo.file.read(MAX_LOGO_BYTES + 1)
        try:
            current.logo_data = _validated_logo(raw)
            current.logo_mime = "image/png"
        except ValueError as exc:
            return HTMLResponse(escape(str(exc)), status_code=422)
    db.commit()
    return HTMLResponse(_page(current, request, "Branding settings saved."))
