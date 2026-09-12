from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select

from app.routers.data_tools import _convert_excel_value, _models

UNASSIGNED_DEVELOPER = "Unassigned / To Verify"


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _find_or_create_developer(db, name: str):
    from app.models import Developer
    name = _clean(name) or UNASSIGNED_DEVELOPER
    row = db.scalar(select(Developer).where(Developer.name == name))
    if not row:
        row = Developer(
            name=name,
            contact=None,
            details="Auto-created import mapping placeholder. Replace with verified developer information before commercial use."
            if name == UNASSIGNED_DEVELOPER else "Imported from property-data staging workbook.",
        )
        db.add(row)
        db.flush()
    return row


def _resolve_developer_name(project_name: str, explicit: str, known_names: list[str]) -> str:
    if explicit:
        return explicit
    normalized = project_name.casefold()
    for name in sorted(known_names, key=len, reverse=True):
        token = name.split("/")[0].strip().casefold()
        if token and normalized.startswith(token):
            return name
    return UNASSIGNED_DEVELOPER


def _read_rows(ws):
    headers = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    for row_no, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(v not in (None, "") for v in values):
            continue
        yield row_no, {headers[i]: values[i] for i in range(min(len(headers), len(values))) if headers[i]}


def _convert(model, raw: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    columns = {c.name: c for c in model.__table__.columns}
    out: dict[str, Any] = {}
    for field in fields:
        if field == "id" or field not in raw or field not in columns:
            continue
        value = _convert_excel_value(columns[field], raw.get(field))
        if field.endswith("_json") and value is not None:
            json.loads(value)
        out[field] = value
    return out


def import_property_workbook(content: bytes, db) -> tuple[int, int, list[str]]:
    """Import the CRM property staging workbook with safe name-based FK resolution.

    The operation is atomic: any validation error rolls back all changes. Projects without
    a verified developer are attached to a clearly named placeholder rather than guessing an ID.
    Configuration rows are converted into Unit rows only when a project can be resolved.
    """
    models = _models()
    wb = load_workbook(BytesIO(content), data_only=True)
    created = updated = 0
    errors: list[str] = []
    project_map: dict[str, int] = {}
    tower_map: dict[tuple[int, str], int] = {}

    try:
        # 1) Developers
        if "Developers" in wb.sheetnames:
            model, fields = models["Developers"]
            for row_no, raw in _read_rows(wb["Developers"]):
                try:
                    row_id = int(raw["id"]) if raw.get("id") not in (None, "") else None
                    obj = db.get(model, row_id) if row_id else db.scalar(select(model).where(model.name == _clean(raw.get("name"))))
                    if obj is None:
                        obj = model(**_convert(model, raw, fields))
                        db.add(obj); db.flush(); created += 1
                    else:
                        for k, v in _convert(model, raw, fields).items(): setattr(obj, k, v)
                        updated += 1
                except Exception as exc:
                    errors.append(f"Developers row {row_no}: {exc}"); break
        if errors: raise ValueError(errors[0])

        # 2) Projects. Resolve developer by explicit reference, obvious existing developer prefix,
        # or the safe placeholder. Never guess a numeric FK.
        if "Projects" in wb.sheetnames:
            model, fields = models["Projects"]
            from app.models import Developer
            known_names = [x for x in db.scalars(select(Developer.name)).all() if x]
            for row_no, raw in _read_rows(wb["Projects"]):
                try:
                    project_name = _clean(raw.get("name"))
                    if not project_name: raise ValueError("name is required")
                    dev_name = _resolve_developer_name(project_name, _clean(raw.get("developer_name_ref")), known_names)
                    developer = _find_or_create_developer(db, dev_name)
                    if dev_name not in known_names: known_names.append(dev_name)
                    values = _convert(model, raw, fields)
                    values["developer_id"] = developer.id
                    row_id = int(raw["id"]) if raw.get("id") not in (None, "") else None
                    obj = db.get(model, row_id) if row_id else None
                    if obj is None and not row_id:
                        obj = model(**values); db.add(obj); db.flush(); created += 1
                    elif obj is None:
                        raise ValueError(f"id {row_id} does not exist")
                    else:
                        for k, v in values.items(): setattr(obj, k, v)
                        updated += 1
                    key = (project_name.casefold(), _clean(raw.get("city")).casefold(), _clean(raw.get("locality")).casefold())
                    project_map["|".join(key)] = obj.id
                except Exception as exc:
                    errors.append(f"Projects row {row_no}: {exc}"); break
        if errors: raise ValueError(errors[0])

        # 3) Optional Towers sheet, resolved by project_id or project name reference.
        if "Towers" in wb.sheetnames:
            model, fields = models["Towers"]
            for row_no, raw in _read_rows(wb["Towers"]):
                try:
                    project_id = raw.get("project_id")
                    if project_id in (None, ""):
                        raise ValueError("project_id is required in Towers sheet")
                    values = _convert(model, raw, fields)
                    row_id = int(raw["id"]) if raw.get("id") not in (None, "") else None
                    obj = db.get(model, row_id) if row_id else None
                    if obj is None and not row_id:
                        obj = model(**values); db.add(obj); db.flush(); created += 1
                    elif obj is None:
                        raise ValueError(f"id {row_id} does not exist")
                    else:
                        for k, v in values.items(): setattr(obj, k, v)
                        updated += 1
                    tower_map[(int(project_id), _clean(raw.get("name")).casefold())] = obj.id
                except Exception as exc:
                    errors.append(f"Towers row {row_no}: {exc}"); break
        if errors: raise ValueError(errors[0])

        # 4) Normalized configuration staging -> Unit records.
        if "Units_Config_Staging" in wb.sheetnames:
            unit_model, unit_fields = models["Units"]
            for row_no, raw in _read_rows(wb["Units_Config_Staging"]):
                try:
                    project_name = _clean(raw.get("project_name_ref"))
                    locality = _clean(raw.get("locality"))
                    matches = [pid for key, pid in project_map.items() if key.startswith(project_name.casefold() + "|") and (not locality or locality.casefold() in key)]
                    if not matches:
                        raise ValueError(f"project '{project_name}' could not be resolved")
                    project_id = matches[0]
                    bhk = _clean(raw.get("bhk")) or "Configuration"
                    amin, amax = raw.get("carpet_area_min"), raw.get("carpet_area_max")
                    carpet = amin if amin not in (None, "") and amax not in (None, "") and float(amin) == float(amax) else None
                    tower_id = None
                    tower_ref = _clean(raw.get("tower_id_ref"))
                    if tower_ref and tower_ref.isdigit():
                        tower_id = int(tower_ref)
                    unit_no = f"CONFIG-{project_id}-{bhk}-{amin}-{amax}-{row_no}".replace(" ", "-")
                    other = {
                        "source": "Units_Config_Staging",
                        "carpet_area_min": amin,
                        "carpet_area_max": amax,
                        "area_unit": _clean(raw.get("area_unit")),
                        "source_price_text": _clean(raw.get("source_price_text")),
                        "building_floor_source": _clean(raw.get("building_floor_source")),
                        "possession_source": _clean(raw.get("possession_source")),
                        "project_website_url": _clean(raw.get("project_website_url")),
                        "image_url": _clean(raw.get("image_url")),
                        "google_maps_url": _clean(raw.get("google_maps_url")),
                    }
                    values = {
                        "project_id": project_id,
                        "tower_id": tower_id,
                        "unit_number": unit_no,
                        "bhk": bhk,
                        "property_type": "APARTMENT",
                        "carpet_area": carpet,
                        "price": raw.get("price_numeric_if_parseable") or None,
                        "availability": "AVAILABLE",
                        "status": "ACTIVE",
                        "rera": _clean(raw.get("rera")) or None,
                        "amenities_json": "[]",
                        "photos_json": json.dumps([_clean(raw.get("image_url"))]) if _clean(raw.get("image_url")) else "[]",
                        "description": f"Imported configuration from source staging. Carpet area: {amin}-{amax} {_clean(raw.get('area_unit'))}. Verify exact inventory before client use.",
                        "other_details": json.dumps(other, ensure_ascii=False),
                    }
                    obj = db.scalar(select(unit_model).where(unit_model.project_id == project_id, unit_model.unit_number == unit_no))
                    if obj is None:
                        db.add(unit_model(**values)); created += 1
                    else:
                        for k, v in values.items(): setattr(obj, k, v)
                        updated += 1
                except Exception as exc:
                    errors.append(f"Units_Config_Staging row {row_no}: {exc}"); break
        if errors: raise ValueError(errors[0])

        db.commit()
    except Exception:
        db.rollback()
    return created, updated, errors
