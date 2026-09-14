"""Dedicated Super Admin routes for the property-data workspace."""

import re

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogShare, CatalogShareVisit, PropertyMedia, PropertySocialProfile
from app.csrf import require_csrf
from app.database import get_db
from app.models import AuditEvent, NearbyLocation, Project, Tower, Unit
from app.crm_plus_models import MarketingCampaign
from app.marketing_models import MarketingLandingVisit, MarketingLeadEvent
from app.routers.property_data import (
    _user,
    download_approved_property_export as _download_approved_property_export,
    download_property_template as _download_property_template,
    export_property_data as _export_property_data,
    import_property_data as _import_property_data,
    load_godrej_nest_test_data as _load_godrej_nest_test_data,
    property_data_page as _property_data_page,
    save_property_data as _save_property_data,
)

router = APIRouter(tags=["property-data", "super-admin"])


def _require_super_admin(request: Request, db: Session):
    actor = _user(request, db)
    return actor if actor and actor.role == "SUPER_ADMIN" else None


def _rewrite_admin_redirect(response, target: str):
    if isinstance(response, RedirectResponse):
        location = response.headers.get("location", "")
        if location.startswith("/admin/property-data"):
            response.headers["location"] = location.replace("/admin/property-data", target, 1)
    return response


def _inject_project_selection(response):
    """Add robust Projects selection controls to the rendered shared table."""
    if not getattr(response, "body", None):
        return response
    html = response.body.decode("utf-8")
    if 'id="property-select-all"' in html or "<h3>Projects Records</h3>" not in html:
        return response
    csrf = _csrf_placeholder(html)
    bulk_form = (
        '<form id="project-bulk-delete" method="post" action="/super-admin/property-data/delete-selected" '
        'onsubmit="return confirm(\'Delete the selected properties and all linked inventory/media/share records? This cannot be undone.\');">'
        f'<input type="hidden" name="csrf_token" value="{csrf}"></form>'
    )
    controls = (
        '<div class="pd-actions" style="align-items:center;margin-bottom:10px;gap:10px">'
        '<label style="display:flex;align-items:center;gap:7px;margin:0;font-weight:700">'
        '<input id="property-select-all" type="checkbox" onchange="toggleAllProperties(this.checked);updatePropertySelectionCount()" style="width:auto"> Select All</label>'
        '<button class="pd-btn danger" type="submit" form="project-bulk-delete">🗑 Delete Selected</button>'
        '<span id="property-selection-count" class="pd-small">0 selected</span></div>'
    )
    table_start = '<table class="pd-table"><thead><tr><th>ID</th><th>Primary Details</th><th>Action</th></tr></thead><tbody>'
    table_replacement = (
        '<table class="pd-table"><thead><tr><th>ID</th><th>Primary Details</th><th>Edit</th><th style="width:90px;text-align:center">Select</th><th>Delete</th></tr></thead><tbody>'
    )
    if table_start in html:
        html = html.replace(table_start, bulk_form + controls + table_replacement, 1)
    row_pattern = re.compile(
        r'<tr>\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>\s*<a class="pd-btn" href="/(?:admin|super-admin)/property-data\?entity=Projects&amp;id=(\d+)">Edit</a>\s*</td>\s*</tr>',
        re.S,
    )

    def replace_row(match):
        project_id = match.group(1)
        details = match.group(2)
        edit_id = match.group(3)
        return (
            f'<tr><td>{project_id}</td><td>{details}</td>'
            f'<td><a class="pd-btn" href="/super-admin/property-data?entity=Projects&amp;id={edit_id}">Edit</a></td>'
            f'<td style="text-align:center"><input class="property-select" type="checkbox" name="project_ids" value="{project_id}" form="project-bulk-delete" onchange="updatePropertySelectionCount()" aria-label="Select property {project_id}" style="width:auto"></td>'
            f'<td><button class="pd-btn danger" type="submit" form="project-bulk-delete" name="project_ids" value="{project_id}" onclick="return confirm(\'Delete this property and all linked records? This cannot be undone.\')">Delete</button></td></tr>'
        )

    html = row_pattern.sub(replace_row, html)
    script = '''<script>
function toggleAllProperties(checked){document.querySelectorAll('.property-select').forEach(function(x){x.checked=checked;});}
function updatePropertySelectionCount(){var n=document.querySelectorAll('.property-select:checked').length;var box=document.getElementById('property-selection-count');if(box)box.textContent=n+' selected';}
document.addEventListener('DOMContentLoaded',updatePropertySelectionCount);
</script>'''
    html = html.replace('</body>', script + '</body>', 1)
    response.body = html.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def _csrf_placeholder(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else ""


@router.get("/super-admin/property-data")
def super_admin_property_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    response = _property_data_page(request, db)
    return _inject_project_selection(response)


@router.get("/super-admin/property-data/template")
def super_admin_property_template(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db): return RedirectResponse("/super-admin/login", status_code=303)
    return _download_property_template(request, db)


@router.post("/super-admin/property-data/load-godrej-nest", dependencies=[Depends(require_csrf)])
def super_admin_load_godrej_nest_test_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db): return RedirectResponse("/super-admin/login", status_code=303)
    return _rewrite_admin_redirect(_load_godrej_nest_test_data(request, db), "/super-admin/property-data")


@router.post("/super-admin/property-data/import", dependencies=[Depends(require_csrf)])
async def super_admin_import_property_data(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not _require_super_admin(request, db): return RedirectResponse("/super-admin/login", status_code=303)
    return _rewrite_admin_redirect(await _import_property_data(request, file, db), "/super-admin/property-data")


@router.post("/super-admin/property-data/save", dependencies=[Depends(require_csrf)])
async def super_admin_save_property_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db): return RedirectResponse("/super-admin/login", status_code=303)
    return _rewrite_admin_redirect(await _save_property_data(request, db), "/super-admin/property-data")


@router.post("/super-admin/property-data/delete-selected", dependencies=[Depends(require_csrf)])
async def super_admin_delete_selected_properties(request: Request, db: Session = Depends(get_db)):
    actor = _require_super_admin(request, db)
    if not actor: return RedirectResponse("/super-admin/login", status_code=303)
    form = await request.form()
    raw_ids = form.getlist("project_ids")
    project_ids = sorted({int(value) for value in raw_ids if str(value).isdigit()})
    if not project_ids:
        return RedirectResponse("/super-admin/property-data?entity=Projects&error=Select+at+least+one+property", status_code=303)
    try:
        projects = db.scalars(select(Project).where(Project.id.in_(project_ids))).all()
        actual_ids = [project.id for project in projects]
        if not actual_ids: return RedirectResponse("/super-admin/property-data?entity=Projects&error=Selected+properties+were+not+found", status_code=303)
        share_ids = db.scalars(select(CatalogShare.id).where(CatalogShare.project_id.in_(actual_ids))).all()
        unit_ids = db.scalars(select(Unit.id).where(Unit.project_id.in_(actual_ids))).all()
        if unit_ids:
            share_ids = sorted(set(share_ids) | set(db.scalars(select(CatalogShare.id).where(CatalogShare.unit_id.in_(unit_ids))).all()))
        campaign_ids = db.scalars(select(MarketingCampaign.id).where(MarketingCampaign.catalog_share_id.in_(share_ids))).all() if share_ids else []
        if campaign_ids:
            db.execute(delete(MarketingLeadEvent).where(MarketingLeadEvent.campaign_id.in_(campaign_ids)))
            db.execute(delete(MarketingLandingVisit).where(MarketingLandingVisit.campaign_id.in_(campaign_ids)))
            db.execute(delete(MarketingCampaign).where(MarketingCampaign.id.in_(campaign_ids)))
        if share_ids:
            db.execute(delete(CatalogShareVisit).where(CatalogShareVisit.share_id.in_(share_ids)))
            db.execute(delete(CatalogShare).where(CatalogShare.id.in_(share_ids)))
        db.execute(delete(PropertySocialProfile).where(PropertySocialProfile.project_id.in_(actual_ids)))
        db.execute(delete(PropertyMedia).where(PropertyMedia.project_id.in_(actual_ids)))
        db.execute(delete(NearbyLocation).where(NearbyLocation.project_id.in_(actual_ids)))
        if unit_ids: db.execute(delete(Unit).where(Unit.id.in_(unit_ids)))
        db.execute(delete(Tower).where(Tower.project_id.in_(actual_ids)))
        db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "Projects", AuditEvent.entity_id.in_([str(x) for x in actual_ids])))
        for project in projects: db.delete(project)
        db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_PROJECTS_BULK_DELETED", entity_type="Projects", entity_id=None, details=f"Deleted project ids: {actual_ids}"))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/super-admin/property-data?entity=Projects&error=Property+delete+failed%3A+" + str(exc).replace(" ", "+")[:300], status_code=303)
    return RedirectResponse(f"/super-admin/property-data?entity=Projects&message=Deleted+{len(actual_ids)}+selected+properties", status_code=303)


@router.get("/super-admin/property-data/export")
def super_admin_export_property_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db): return RedirectResponse("/super-admin/login", status_code=303)
    return _export_property_data(request, db)


@router.get("/super-admin/property-data/export/download/{request_id}")
def super_admin_download_property_export(request: Request, request_id: int, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db): return RedirectResponse("/super-admin/login", status_code=303)
    return _rewrite_admin_redirect(_download_approved_property_export(request, request_id, db), "/super-admin/property-data")
