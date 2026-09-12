"""Dedicated Super Admin routes for the property-data workspace.

These routes intentionally reuse the property-data implementation while exposing
separate Super Admin URLs. This prevents the Super Admin UI from depending on
/admin/property-data URLs and keeps the portal boundary explicit.
"""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
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


@router.get("/super-admin/property-data")
def super_admin_property_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    return _property_data_page(request, db)


@router.get("/super-admin/property-data/template")
def super_admin_property_template(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    return _download_property_template(request, db)


@router.post("/super-admin/property-data/load-godrej-nest", dependencies=[Depends(require_csrf)])
def super_admin_load_godrej_nest_test_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    response = _load_godrej_nest_test_data(request, db)
    return _rewrite_admin_redirect(response, "/super-admin/property-data")


@router.post("/super-admin/property-data/import", dependencies=[Depends(require_csrf)])
async def super_admin_import_property_data(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    response = await _import_property_data(request, file, db)
    return _rewrite_admin_redirect(response, "/super-admin/property-data")


@router.post("/super-admin/property-data/save", dependencies=[Depends(require_csrf)])
async def super_admin_save_property_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    response = await _save_property_data(request, db)
    return _rewrite_admin_redirect(response, "/super-admin/property-data")


@router.get("/super-admin/property-data/export")
def super_admin_export_property_data(request: Request, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    return _export_property_data(request, db)


@router.get("/super-admin/property-data/export/download/{request_id}")
def super_admin_download_property_export(request: Request, request_id: int, db: Session = Depends(get_db)):
    if not _require_super_admin(request, db):
        return RedirectResponse("/super-admin/login", status_code=303)
    response = _download_approved_property_export(request, request_id, db)
    return _rewrite_admin_redirect(response, "/super-admin/property-data")
