from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.property_master import FACILITY_GROUPS, property_field_groups, PropertyUpdateSource
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
    return templates.TemplateResponse("property_update.html", {
        "request": request, "groups": property_field_groups(), "facility_groups": FACILITY_GROUPS,
        "csrf_token": csrf_token(request), "property_id": request.query_params.get("property_id", ""),
        "error": request.query_params.get("error"), "message": request.query_params.get("message"),
    })

@router.post("/admin/property-update", dependencies=[Depends(require_csrf)])
async def property_update_submit(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in {"ADMIN", "SUPER_ADMIN"}:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    property_id = str(form.get("property_id") or "").strip()
    payload = {k:v for k,v in form.items() if k not in {"csrf_token","property_id"}}
    configs = []
    i = 0
    while i <= 100:
        keys = [f"configurations[{i}][{x}]" for x in ("configuration","carpet_area","price_including_all","rate_per_sqft","bundle_rate","negotiation","availability")]
        vals = [str(form.get(k) or "").strip() for k in keys]
        if not any(vals):
            if i == 0: i += 1; continue
            break
        configs.append(dict(zip(("configuration","carpet_area","price_including_all","rate_per_sqft","bundle_rate","negotiation","availability"), vals)))
        i += 1
    if configs: payload["configurations"] = configs
    towers = []
    i = 0
    while i <= 50:
        keys = [f"tower_details[{i}][{x}]" for x in ("tower_name","total_floors","possession_date")]
        vals = [str(form.get(k) or "").strip() for k in keys]
        if not any(vals):
            if i == 0: i += 1; continue
            break
        towers.append(dict(zip(("tower_name","total_floors","possession_date"), vals)))
        i += 1
    if towers: payload["tower_details"] = towers
    payload["facilities"] = form.getlist("facilities")
    try:
        project, _ = apply_property_master(db, payload=payload, source=PropertyUpdateSource.INDIVIDUAL,
                                           actor=actor, project_id=int(property_id) if property_id else None,
                                           create=not bool(property_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/admin/property-update?error=" + str(exc).replace(" ","+")[:350], status_code=303)
    return RedirectResponse(f"/admin/property-update?property_id={project.id}&message=Property+{project.id}+saved+successfully", status_code=303)
