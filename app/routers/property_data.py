from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent
from app.routers.data_tools import _convert_excel_value, _import_workbook, _models, _save_workbook, _template_workbook

router = APIRouter(tags=["property-data"])
templates = Jinja2Templates(directory="app/templates")
PROPERTY_SHEETS = ("Developers", "Projects", "Towers", "Units", "NearbyLocations")
PROPERTY_MODELS = {name: _models()[name] for name in PROPERTY_SHEETS}


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _guard(request: Request, db: Session):
    user = _user(request, db)
    if not user or user.role not in {"SUPER_ADMIN", "ADMIN"}:
        return None
    return user


def _property_workbook() -> BytesIO:
    source = _template_workbook()
    from openpyxl import load_workbook
    full = load_workbook(source)
    keep = {"Instructions", "Examples", *PROPERTY_SHEETS}
    for sheet in list(full.sheetnames):
        if sheet not in keep:
            del full[sheet]
    ws = full["Instructions"]
    ws.append(["Property-only workflow"])
    ws.append(["Use Projects, Towers, Units and NearbyLocations for property inventory. Use an existing id to update; leave id blank for a new record."])
    return _save_workbook(full)


def _display_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


@router.get("/admin/property-data", response_class=HTMLResponse)
def property_data_page(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    selected = request.query_params.get("entity", "Projects")
    if selected not in PROPERTY_MODELS:
        selected = "Projects"
    model, fields = PROPERTY_MODELS[selected]
    rows = db.scalars(select(model).order_by(model.id.desc()).limit(100)).all()
    editing_id = request.query_params.get("id")
    edit_row = db.get(model, int(editing_id)) if editing_id and editing_id.isdigit() else None
    return templates.TemplateResponse("property_data.html", {
        "request": request, "username": actor.username, "role": actor.role, "avatar": actor.username[:1].upper(),
        "csrf_token": csrf_token(request), "entities": PROPERTY_SHEETS, "selected": selected, "fields": fields,
        "rows": rows, "edit_row": edit_row, "display_value": _display_value, "getattr": getattr,
        "message": request.query_params.get("message"), "error": request.query_params.get("error"),
        "show_user_management": actor.role in {"SUPER_ADMIN", "ADMIN"}, "show_integrations": False,
        "show_alerts": False, "show_approvals": actor.role in {"SUPER_ADMIN", "ADMIN"},
    })


@router.get("/admin/property-data/template")
def download_property_template(request: Request, db: Session = Depends(get_db)):
    if not _guard(request, db):
        return RedirectResponse("/", status_code=303)
    workbook = _property_workbook()
    return StreamingResponse(workbook, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=MetroCRM_Property_Data_Template.xlsx"})


@router.post("/admin/property-data/import", dependencies=[Depends(require_csrf)])
async def import_property_data(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return RedirectResponse("/admin/property-data?error=Only+Excel+.xlsx+files+are+supported", status_code=303)
    content = await file.read()
    created, updated, errors = _import_workbook(content, db)
    if errors:
        return RedirectResponse("/admin/property-data?error=" + str(errors[0]).replace(" ", "+")[:350], status_code=303)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_DATA_IMPORTED", entity_type="PropertyData", entity_id=None, details=json.dumps({"filename": file.filename, "created": created, "updated": updated})))
    db.commit()
    return RedirectResponse(f"/admin/property-data?message=Imported+{created}+new+and+updated+{updated}+property+records", status_code=303)


@router.post("/admin/property-data/save", dependencies=[Depends(require_csrf)])
async def save_property_data(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    entity = str(form.get("entity", "Projects"))
    if entity not in PROPERTY_MODELS:
        return RedirectResponse("/admin/property-data?error=Invalid+property+type", status_code=303)
    model, fields = PROPERTY_MODELS[entity]
    raw_id = str(form.get("id", "")).strip()
    try:
        obj = db.get(model, int(raw_id)) if raw_id else model()
        if raw_id and obj is None:
            raise ValueError("Record ID does not exist")
        columns = {column.name: column for column in model.__table__.columns}
        for field in fields:
            if field == "id" or field not in columns:
                continue
            value = form.get(field)
            converted = _convert_excel_value(columns[field], value)
            if field.endswith("_json") and converted is not None:
                json.loads(converted)
            setattr(obj, field, converted)
        db.add(obj)
        db.flush()
        action = "PROPERTY_RECORD_UPDATED" if raw_id else "PROPERTY_RECORD_CREATED"
        db.add(AuditEvent(actor_user_id=actor.id, action=action, entity_type=entity, entity_id=str(obj.id), details=json.dumps({"online_editor": True})))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/admin/property-data?entity={entity}&error=" + str(exc).replace(" ", "+")[:350], status_code=303)
    return RedirectResponse(f"/admin/property-data?entity={entity}&id={obj.id}&message=Property+record+saved", status_code=303)
