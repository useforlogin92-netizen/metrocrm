from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from openpyxl import load_workbook
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Booking, Commission, DataRequest, Developer, NearbyLocation, Project, SiteVisit, Token, Tower, Unit, User
from app.routers.data_tools import _convert_excel_value, _export_workbook, _import_workbook, _models, _save_workbook, _template_workbook
from tools.seed_godrej_nest_test import seed_godrej_nest_test

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
    search = request.query_params.get("search", "").strip()[:120]
    if search:
        pattern = f"%{search}%"
        if selected == "Projects":
            project_columns = [
                Project.id, Project.name, Project.state, Project.district, Project.city,
                Project.locality, Project.sector, Project.address, Project.pincode,
                Project.latitude, Project.longitude, Project.rera, Project.possession_date,
                Project.builder_commitment_date, Project.construction_status,
                Project.amenities_json, Project.photos_json, Project.brochure, Project.description,
            ]
            unit_columns = [
                Unit.id, Unit.unit_number, Unit.bhk, Unit.property_type, Unit.carpet_area,
                Unit.built_up_area, Unit.super_built_up_area, Unit.plot_area, Unit.price,
                Unit.price_per_sqft, Unit.parking, Unit.facing, Unit.furnishing, Unit.possession,
                Unit.rera, Unit.availability, Unit.status, Unit.amenities_json,
                Unit.photos_json, Unit.floor_plan, Unit.brochure, Unit.description, Unit.other_details,
            ]
            conditions = [cast(column, String).ilike(pattern) for column in project_columns]
            conditions.append(cast(Developer.name, String).ilike(pattern))
            unit_match = select(Unit.id).where(
                Unit.project_id == Project.id,
                or_(*[cast(column, String).ilike(pattern) for column in unit_columns]),
            ).exists()
            conditions.append(unit_match)
            stmt = select(Project).outerjoin(Developer, Developer.id == Project.developer_id).where(or_(*conditions))
        else:
            columns = [column for column in model.__table__.columns]
            stmt = select(model).where(or_(*[cast(column, String).ilike(pattern) for column in columns]))
        rows = db.scalars(stmt.order_by(model.id.desc()).limit(100)).all()
    else:
        rows = db.scalars(select(model).order_by(model.id.desc()).limit(100)).all()
    editing_id = request.query_params.get("id")
    edit_row = db.get(model, int(editing_id)) if editing_id and editing_id.isdigit() else None
    export_requests = db.scalars(
        select(DataRequest)
        .where(DataRequest.requester_id == actor.id, DataRequest.action == "EXPORT", DataRequest.entity_type == "PropertyData")
        .order_by(DataRequest.id.desc()).limit(10)
    ).all()
    return templates.TemplateResponse("property_data.html", {
        "request": request, "username": actor.username, "role": actor.role, "avatar": actor.username[:1].upper(),
        "csrf_token": csrf_token(request), "entities": PROPERTY_SHEETS, "selected": selected, "fields": fields,
        "rows": rows, "edit_row": edit_row, "display_value": _display_value, "getattr": getattr, "search": search,
        "export_requests": export_requests,
        "message": request.query_params.get("message"), "error": request.query_params.get("error"),
        "show_user_management": actor.role in {"SUPER_ADMIN", "ADMIN"}, "show_integrations": False,
        "show_alerts": False, "show_approvals": actor.role in {"SUPER_ADMIN", "ADMIN"},
    })


@router.post("/admin/property-data/load-godrej-nest", dependencies=[Depends(require_csrf)])
def load_godrej_nest_test_data(request: Request, db: Session = Depends(get_db)):
    """Explicitly load the reviewed Godrej Nest test inventory into Property Data."""
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    try:
        project_id, unit_count, gallery_count = seed_godrej_nest_test(db)
        db.add(AuditEvent(actor_user_id=actor.id, action="GODREJ_NEST_TEST_DATA_LOADED", entity_type="Projects", entity_id=str(project_id), details=json.dumps({"units": unit_count, "gallery_images": gallery_count, "source": "reviewed test seed"})))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/admin/property-data?entity=Projects&error=Godrej+Nest+test+data+load+failed%3A+" + str(exc).replace(" ", "+")[:300], status_code=303)
    return RedirectResponse(f"/admin/property-data?entity=Projects&message=Godrej+Nest+test+property+loaded+%28project+%23{project_id}%2C+{unit_count}+units%2C+{gallery_count}+gallery+images%29", status_code=303)


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


@router.post("/admin/property-data/bulk-modify", dependencies=[Depends(require_csrf)])
async def bulk_modify_property_data(request: Request, db: Session = Depends(get_db)):
    """Apply explicitly supplied fields to multiple selected Projects."""
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    raw_ids = form.getlist("project_ids")
    project_ids = []
    for raw_id in raw_ids:
        try:
            project_ids.append(int(str(raw_id)))
        except (TypeError, ValueError):
            continue
    project_ids = list(dict.fromkeys(project_ids))
    if not project_ids:
        return RedirectResponse("/admin/property-data?entity=Projects&error=Select+at+least+one+property", status_code=303)

    allowed_fields = ("city", "locality", "address", "rera")
    values = {field: str(form.get(field, "")).strip() for field in allowed_fields}
    supplied = {field: value for field, value in values.items() if value}
    if not supplied:
        return RedirectResponse("/admin/property-data?entity=Projects&error=Enter+at+least+one+field+to+modify", status_code=303)

    try:
        rows = db.scalars(select(PROPERTY_MODELS["Projects"][0]).where(PROPERTY_MODELS["Projects"][0].id.in_(project_ids))).all()
        found = {row.id: row for row in rows}
        missing = [str(pid) for pid in project_ids if pid not in found]
        if missing:
            raise ValueError("Property ID not found: " + ", ".join(missing[:10]))
        for row in rows:
            for field, value in supplied.items():
                setattr(row, field, value)
            db.add(AuditEvent(
                actor_user_id=actor.id,
                action="PROPERTY_RECORD_BULK_UPDATED",
                entity_type="Projects",
                entity_id=str(row.id),
                details=json.dumps({"fields": list(supplied.keys()), "bulk_count": len(rows), "online_editor": True}),
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/admin/property-data?entity=Projects&error=" + str(exc).replace(" ", "+")[:350], status_code=303)
    return RedirectResponse("/admin/property-data?entity=Projects&message=Updated+" + str(len(rows)) + "+properties+successfully", status_code=303)


@router.post("/super-admin/property-data/projects/{project_id}/delete", dependencies=[Depends(require_csrf)])
def delete_single_property_data(project_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/dashboard", status_code=303)
    if not db.get(Project, project_id):
        return RedirectResponse("/super-admin/property-data?entity=Projects&error=Property+not+found", status_code=303)
    return _delete_single_property_data(project_id, actor, db)


def _delete_single_property_data(project_id: int, actor: User, db: Session):
    try:
        if db.scalar(select(Booking.id).where(Booking.project_id == project_id).limit(1)) or db.scalar(select(Commission.id).where(Commission.project_id == project_id).limit(1)) or db.scalar(select(SiteVisit.id).where(SiteVisit.project_id == project_id).limit(1)) or db.scalar(select(Token.id).where(Token.project_id == project_id).limit(1)):
            raise ValueError("Cannot delete property with linked booking, commission, site visit or token records")
        unit_ids = db.scalars(select(Unit.id).where(Unit.project_id == project_id)).all()
        db.query(NearbyLocation).filter(NearbyLocation.project_id == project_id).delete(synchronize_session=False)
        if unit_ids:
            db.query(Token).filter(Token.unit_id.in_(unit_ids)).update({Token.unit_id: None}, synchronize_session=False)
            db.query(Booking).filter(Booking.unit_id.in_(unit_ids)).update({Booking.unit_id: None}, synchronize_session=False)
        db.query(Unit).filter(Unit.project_id == project_id).delete(synchronize_session=False)
        db.query(Tower).filter(Tower.project_id == project_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_RECORD_DELETED", entity_type="Projects", entity_id=str(project_id), details=json.dumps({"property_only_records": True})))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/super-admin/property-data?entity=Projects&error=" + str(exc).replace(" ", "+")[:350], status_code=303)
    return RedirectResponse("/super-admin/property-data?entity=Projects&message=Property+" + str(project_id) + "+deleted+successfully", status_code=303)


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


def _create_export_request(actor: User, db: Session):
    entities = list(PROPERTY_SHEETS)
    pending = db.scalar(select(DataRequest).where(DataRequest.requester_id == actor.id, DataRequest.action == "EXPORT", DataRequest.entity_type == "PropertyData", DataRequest.status == "PENDING").order_by(DataRequest.id.desc()))
    if pending:
        return False
    request_row = DataRequest(requester_id=actor.id, action="EXPORT", entity_type="PropertyData", filters_json=json.dumps({"entities": entities}), reason="Admin requested property data export", status="PENDING")
    db.add(request_row)
    db.flush()
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_EXPORT_REQUESTED", entity_type="PropertyData", entity_id=str(request_row.id), details=json.dumps({"entities": entities, "status": "PENDING"})))
    db.commit()
    return True


@router.get("/admin/property-data/export")
def export_property_data(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    if actor.role == "ADMIN":
        return RedirectResponse("/admin/property-data?error=Admin+must+submit+an+export+approval+request", status_code=303)
    entities = list(PROPERTY_SHEETS)
    workbook = _export_workbook(entities, db)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_DATA_EXPORTED", entity_type="PropertyData", entity_id=None, details=json.dumps({"entities": entities, "approval": "direct"})))
    db.commit()
    return StreamingResponse(workbook, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=MetroCRM_Property_Data_Export.xlsx"})


@router.post("/admin/property-data/export/request", dependencies=[Depends(require_csrf)])
def request_property_export(request: Request, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    if actor.role != "ADMIN":
        return RedirectResponse("/admin/property-data/export", status_code=303)
    created = _create_export_request(actor, db)
    if not created:
        return RedirectResponse("/admin/property-data?error=Export+approval+already+pending", status_code=303)
    return RedirectResponse("/admin/property-data?message=Export+request+sent+to+Super+Admin+for+approval", status_code=303)


@router.get("/admin/property-data/export/download/{request_id}")
def download_approved_property_export(request: Request, request_id: int, db: Session = Depends(get_db)):
    actor = _guard(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    row = db.get(DataRequest, request_id)
    if not row or row.action != "EXPORT" or row.entity_type != "PropertyData" or row.status != "APPROVED":
        return RedirectResponse("/admin/property-data?error=Export+approval+not+available", status_code=403)
    if actor.role != "SUPER_ADMIN" and row.requester_id != actor.id:
        return RedirectResponse("/admin/property-data?error=You+can+only+download+your+own+approved+export", status_code=403)
    try:
        details = json.loads(row.filters_json or "{}")
        entities = [x for x in details.get("entities", []) if x in PROPERTY_SHEETS]
    except (TypeError, ValueError):
        entities = list(PROPERTY_SHEETS)
    workbook = _export_workbook(entities or list(PROPERTY_SHEETS), db)
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_DATA_EXPORTED", entity_type="PropertyData", entity_id=str(row.id), details=json.dumps({"entities": entities, "approval_request_id": row.id, "approved_by": row.decided_by_id})))
    db.commit()
    return StreamingResponse(workbook, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=MetroCRM_Property_Data_Export.xlsx"})


@router.get("/super-admin/property-data-export-requests", response_class=HTMLResponse)
def property_export_requests(request: Request, db: Session = Depends(get_db)):
    actor = _user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/dashboard", status_code=303)
    rows = db.scalars(select(DataRequest).where(DataRequest.action == "EXPORT", DataRequest.entity_type == "PropertyData").order_by(DataRequest.id.desc()).limit(100)).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.requester_id for r in rows}))).all()} if rows else {}
    html = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | Property Export Approvals</title><style>body{font-family:Inter,Arial,sans-serif;background:#f5f7fb;margin:0;padding:32px;color:#10213f}.wrap{max-width:1050px;margin:auto}.card{background:#fff;border-radius:16px;padding:24px;box-shadow:0 8px 30px #0001}.row{padding:16px 0;border-top:1px solid #e5eaf2}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:0;border-radius:9px;padding:9px 14px;font-weight:700;cursor:pointer}.approve{background:#16803c;color:#fff}.reject{background:#c62828;color:#fff}.muted{color:#64748b;font-size:12px}.pill{display:inline-block;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:700}</style></head><body><div class='wrap'><div class='card'><h1>Property Data Export Approvals</h1><p class='muted'>Admin exports require explicit Super Admin approval. Approved requests can then be downloaded by the requesting Admin.</p>"]
    for row in rows:
        user = users.get(row.requester_id)
        status = row.status
        if status == "PENDING":
            actions = f"<div class='actions'><form method='post' action='/super-admin/property-data-export-requests/{row.id}/approve'><input type='hidden' name='csrf_token' value='{csrf_token(request)}'><button class='btn approve'>Approve Export</button></form><form method='post' action='/super-admin/property-data-export-requests/{row.id}/reject'><input type='hidden' name='csrf_token' value='{csrf_token(request)}'><button class='btn reject'>Reject</button></form></div>"
        else:
            actions = ""
        html.append(f"<div class='row'><b>{user.username if user else 'Unknown user'}</b> · <span class='pill'>{status}</span><div class='muted'>Request #{row.id} · {row.created_at} · {row.reason}</div>{actions}</div>")
    if not rows:
        html.append("<div class='row muted'>No property export requests.</div>")
    html.append("</div></div></body></html>")
    return HTMLResponse("".join(html))


def _decide_property_export(actor: User | None, request_id: int, approve: bool, db: Session):
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/dashboard", status_code=303)
    row = db.get(DataRequest, request_id)
    if not row or row.action != "EXPORT" or row.entity_type != "PropertyData" or row.status != "PENDING":
        return RedirectResponse("/super-admin/property-data-export-requests", status_code=303)
    row.status = "APPROVED" if approve else "REJECTED"
    row.decided_by_id = actor.id
    row.decided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.approval_reason = "Approved by Super Admin" if approve else "Rejected by Super Admin"
    db.add(AuditEvent(actor_user_id=actor.id, action="PROPERTY_EXPORT_APPROVED" if approve else "PROPERTY_EXPORT_REJECTED", entity_type="PropertyData", entity_id=str(row.id), details=json.dumps({"requester_id": row.requester_id})))
    db.commit()
    return RedirectResponse("/super-admin/property-data-export-requests", status_code=303)


@router.post("/super-admin/property-data-export-requests/{request_id}/approve", dependencies=[Depends(require_csrf)])
def approve_property_export(request: Request, request_id: int, db: Session = Depends(get_db)):
    return _decide_property_export(_user(request, db), request_id, True, db)


@router.post("/super-admin/property-data-export-requests/{request_id}/reject", dependencies=[Depends(require_csrf)])
def reject_property_export(request: Request, request_id: int, db: Session = Depends(get_db)):
    return _decide_property_export(_user(request, db), request_id, False, db)
