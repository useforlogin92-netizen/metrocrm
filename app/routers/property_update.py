from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import User
from app.property_master import PROPERTY_MASTER_FIELDS, PropertyUpdateSource
from app.services.property_update_engine import apply_property_master

router = APIRouter(tags=["property-update"])
templates = Jinja2Templates(directory="app/templates")


def _actor(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


@router.get("/admin/property-update", response_class=HTMLResponse)
def property_update_page(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in {"ADMIN", "SUPER_ADMIN"}:
        return RedirectResponse("/", status_code=303)
    groups = {}
    for field in PROPERTY_MASTER_FIELDS:
        groups.setdefault(field.group, []).append(field)
    return templates.TemplateResponse(
        "property_update.html",
        {
            "request": request,
            "groups": groups,
            "csrf_token": csrf_token(request),
            "property_id": request.query_params.get("property_id", ""),
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@router.post("/admin/property-update", dependencies=[Depends(require_csrf)])
async def property_update_submit(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in {"ADMIN", "SUPER_ADMIN"}:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    property_id = str(form.get("property_id") or "").strip()
    payload = {k: v for k, v in form.items() if k not in {"csrf_token", "property_id", "developer"}}
    payload["developer"] = form.get("developer")

    configurations = []
    index = 0
    while True:
        config = str(form.get(f"configurations[{index}][configuration]") or "").strip()
        area = str(form.get(f"configurations[{index}][carpet_area]") or "").strip()
        total = str(form.get(f"configurations[{index}][price_including_all]") or "").strip()
        rate = str(form.get(f"configurations[{index}][rate_per_sqft]") or "").strip()
        negotiation = str(form.get(f"configurations[{index}][negotiation]") or "").strip()
        if not any((config, area, total, rate, negotiation)):
            if index > 0:
                break
            index += 1
            continue
        configurations.append({
            "configuration": config,
            "carpet_area": area,
            "price_including_all": total,
            "rate_per_sqft": rate,
            "negotiation": negotiation,
        })
        index += 1
        if index > 100:
            break
    if configurations:
        payload["configurations"] = configurations

    try:
        project, _ = apply_property_master(
            db,
            payload=payload,
            source=PropertyUpdateSource.INDIVIDUAL,
            actor=actor,
            project_id=int(property_id) if property_id else None,
            create=not bool(property_id),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/admin/property-update?error=" + str(exc).replace(" ", "+")[:350], status_code=303)
    return RedirectResponse("/admin/property-update?property_id=" + str(project.id) + "&message=Property+" + str(project.id) + "+saved+successfully", status_code=303)
