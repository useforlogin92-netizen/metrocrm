from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import Unit, Tower
from app.realestate_finance_models import CostSheet, PropertyQuotation
from app.routers.accounting import router as accounting_router

router = APIRouter(tags=["real-estate-finance"])
router.include_router(accounting_router)


def current_user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def page(body: str) -> HTMLResponse:
    return HTMLResponse("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | Cost Sheet</title><style>body{font-family:Arial;background:#f5f7fb;padding:24px;color:#10213f}.wrap{max-width:1100px;margin:auto}.card{background:#fff;padding:20px;border:1px solid #e5eaf2;border-radius:15px;margin-bottom:18px}h1{margin-top:0}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;font-size:12px;font-weight:700;margin:8px 0 4px}input,select,textarea{width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px}.btn{display:inline-block;border:0;border-radius:8px;padding:9px 13px;background:#2563eb;color:#fff;font-weight:700;cursor:pointer;text-decoration:none;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:9px;border-bottom:1px solid #eef2f7;text-align:left}th{background:#f8fafc}@media(max-width:700px){.two{grid-template-columns:1fr}}</style></head><body><div class='wrap'><h1>Cost Sheet & Quotations</h1>{body}</div></body></html>")


def money(value: Decimal | int | float | None) -> Decimal:
    return Decimal(str(value or 0))


@router.get("/crm/advanced/cost-sheets", response_class=HTMLResponse)
def cost_sheets_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor: return RedirectResponse("/", status_code=303)
    units = db.scalars(select(Unit).order_by(Unit.id.desc()).limit(100)).all()
    sheets = db.scalars(select(CostSheet).order_by(CostSheet.id.desc()).limit(100)).all()
    csrf = csrf_token(request)
    form = "<div class='card'><h2>Create cost sheet</h2><p>India-ready pricing components: base price, PLC, floor rise, parking, GST, stamp duty, registration and other charges.</p><form method='post' action='/crm/advanced/cost-sheets'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Unit</label><select name='unit_id'>"+"".join(f"<option value='{u.id}'>#{u.id} {escape(u.unit_number)}</option>" for u in units)+"</select></div><div><label>Base Price</label><input name='base_price' type='number' step='0.01' value='0'></div><div><label>PLC</label><input name='plc' type='number' step='0.01' value='0'></div><div><label>Floor Rise</label><input name='floor_rise' type='number' step='0.01' value='0'></div><div><label>Parking</label><input name='parking' type='number' step='0.01' value='0'></div><div><label>GST</label><input name='gst' type='number' step='0.01' value='0'></div><div><label>Stamp Duty</label><input name='stamp_duty' type='number' step='0.01' value='0'></div><div><label>Registration</label><input name='registration' type='number' step='0.01' value='0'></div><div><label>Other Charges</label><input name='other_charges' type='number' step='0.01' value='0'></div></div><button class='btn' type='submit'>Calculate & Save</button></form></div>"
    table = "<div class='card'><h2>Saved cost sheets</h2><table><tr><th>ID</th><th>Unit</th><th>Base</th><th>Extras</th><th>Total</th></tr>" + "".join(f"<tr><td>#{s.id}</td><td>#{s.unit_id}</td><td>₹ {float(s.base_price):,.2f}</td><td>₹ {float(s.total_amount-s.base_price):,.2f}</td><td><strong>₹ {float(s.total_amount):,.2f}</strong></td></tr>" for s in sheets) + "</table></div>"
    return page(form + table)


@router.post("/crm/advanced/cost-sheets", dependencies=[Depends(require_csrf)])
def create_cost_sheet(request: Request, unit_id: int = Form(...), base_price: Decimal = Form(0), plc: Decimal = Form(0), floor_rise: Decimal = Form(0), parking: Decimal = Form(0), gst: Decimal = Form(0), stamp_duty: Decimal = Form(0), registration: Decimal = Form(0), other_charges: Decimal = Form(0), db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or not db.get(Unit, unit_id): return RedirectResponse("/crm/advanced/cost-sheets", status_code=303)
    total = sum((base_price, plc, floor_rise, parking, gst, stamp_duty, registration, other_charges), Decimal("0"))
    db.add(CostSheet(unit_id=unit_id, base_price=base_price, plc=plc, floor_rise=floor_rise, parking=parking, gst=gst, stamp_duty=stamp_duty, registration=registration, other_charges=other_charges, total_amount=total, created_by_id=actor.id)); db.commit()
    return RedirectResponse("/crm/advanced/cost-sheets", status_code=303)


def _unit_status_bucket(unit: Unit) -> str:
    raw = str(unit.status or unit.availability or "").strip().upper()
    if raw in {"BOOKED", "SOLD", "ALLOCATED", "CLOSED"} or "BOOKED" in raw:
        return "BOOKED"
    if "HOLD" in raw or "RESERVED" in raw:
        return "HOLD"
    if raw in {"AVAILABLE", "VACANT", "OPEN"}:
        return "AVAILABLE"
    return "UNKNOWN"


@router.get("/crm/advanced/unit-matrix", response_class=HTMLResponse)
def unit_matrix(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    units = db.scalars(select(Unit).order_by(Unit.tower_id, Unit.floor, Unit.unit_number)).all()
    tower_ids = {unit.tower_id for unit in units if unit.tower_id is not None}
    towers = db.scalars(select(Tower).where(Tower.id.in_(tower_ids))).all() if tower_ids else []
    tower_names = {tower.id: tower.name for tower in towers}
    cells = []
    tower_options = sorted({tower_names.get(unit.tower_id, "No tower") for unit in units})
    floor_options = sorted({str(unit.floor) if unit.floor is not None else "Unknown" for unit in units})
    for unit in units:
        status = _unit_status_bucket(unit)
        tower = tower_names.get(unit.tower_id, "No tower")
        floor = str(unit.floor) if unit.floor is not None else "Unknown"
        configuration = escape(unit.bhk or unit.property_type or "Configuration not set")
        cells.append(f"<article class='unit' data-status='{status}' data-tower='{escape(tower)}' data-floor='{escape(floor)}'><strong>{escape(unit.unit_number)}</strong><span>{escape(tower)} · Floor {escape(floor)}</span><b class='status-{status.lower()}'>{status}</b><small>{configuration}</small></article>")
    tower_select = "".join(f"<option value=\"{escape(t)}\">{escape(t)}</option>" for t in tower_options)
    floor_select = "".join(f"<option value=\"{escape(f)}\">{escape(f)}</option>" for f in floor_options)
    body = f"""<section class=card><h2>Live Property Unit Matrix</h2><p>Inventory status is read from the existing unit records. Unknown or blank statuses are shown as UNKNOWN rather than assumed available.</p>
<div class=filters><label>Status<select id=status-filter><option value="">All statuses</option><option>AVAILABLE</option><option>BOOKED</option><option>HOLD</option><option>UNKNOWN</option></select></label>
<label>Tower / Wing<select id=tower-filter><option value="">All towers</option>{tower_select}</select></label>
<label>Floor<select id=floor-filter><option value="">All floors</option>{floor_select}</select></label></div>
<div class=legend><span class=available>Available</span><span class=booked>Booked</span><span class=hold>Hold</span><span class=unknown>Unknown</span></div>
<div id=unit-grid class=unit-grid>{"".join(cells) or "<p>No units found. Import property inventory first.</p>"}</div><p id=empty-state hidden>No units match these filters.</p>
<p><a class=btn href=/crm/advanced/cost-sheets>Open Cost Sheets</a> <a class=btn href=/dashboard>Dashboard</a></p></section>
<style>.filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0}.filters label{font-weight:700}.filters select{display:block;width:100%;padding:9px;border:1px solid #cbd5e1;border-radius:8px;margin-top:5px}.unit-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}.unit{border:1px solid #dbe4ef;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:7px;background:#fff}.unit span,.unit small{font-size:12px;color:#64748b}.status-available{color:#166534}.status-booked{color:#991b1b}.status-hold{color:#92400e}.status-unknown{color:#475569}.legend{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.legend span{padding:5px 9px;border-radius:20px;font-size:12px}.available{background:#dcfce7;color:#166534}.booked{background:#fee2e2;color:#991b1b}.hold{background:#fef3c7;color:#92400e}.unknown{background:#e2e8f0;color:#334155}@media(max-width:650px){.filters{grid-template-columns:1fr}}</style>
<script>(function(){const filters=["status","tower","floor"].map(k=>document.getElementById(k+"-filter"));const cards=Array.from(document.querySelectorAll(".unit"));const empty=document.getElementById("empty-state");function apply(){let shown=0;cards.forEach(card=>{const ok=filters.every((input,i)=>!input.value||card.dataset[["status","tower","floor"][i]]===input.value);card.hidden=!ok;if(ok)shown++;});empty.hidden=shown>0;}filters.forEach(input=>input.addEventListener("change",apply));})();</script>"""
    return page(body)

@router.get("/crm/advanced/quotations", response_class=HTMLResponse)
def quotations_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor: return RedirectResponse("/", status_code=303)
    rows = db.scalars(select(PropertyQuotation).order_by(PropertyQuotation.id.desc()).limit(100)).all(); csrf=csrf_token(request)
    body = "<div class='card'><h2>Quotation register</h2><p class='muted'>Create a traceable quotation from a saved cost sheet. Final pricing remains controlled by your business approval process.</p><form method='post' action='/crm/advanced/quotations'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Cost Sheet ID</label><input name='cost_sheet_id' type='number' required></div><div><label>Quotation Number</label><input name='quotation_no' required placeholder='MQ-2026-0001'></div><div><label>Lead ID (optional)</label><input name='lead_id' type='number'></div><div><label>Customer ID (optional)</label><input name='customer_id' type='number'></div><div><label>Unit ID (optional)</label><input name='unit_id' type='number'></div><div><label>Valid Until</label><input name='valid_until' type='date'></div></div><label>Notes</label><textarea name='notes'></textarea><button class='btn' type='submit'>Create Quotation</button></form></div>"
    body += "<div class='card'><table><tr><th>No.</th><th>Cost Sheet</th><th>Total</th><th>Status</th><th>Valid Until</th></tr>"+"".join(f"<tr><td>{escape(r.quotation_no)}</td><td>#{r.cost_sheet_id}</td><td>₹ {float(r.total_amount):,.2f}</td><td>{escape(r.status)}</td><td>{r.valid_until.date() if r.valid_until else '—'}</td></tr>" for r in rows)+"</table></div>"
    return page(body)


@router.post("/crm/advanced/quotations", dependencies=[Depends(require_csrf)])
def create_quotation(request: Request, cost_sheet_id: int = Form(...), quotation_no: str = Form(...), lead_id: int | None = Form(None), customer_id: int | None = Form(None), unit_id: int | None = Form(None), valid_until: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db)):
    actor=current_user(request,db); sheet=db.get(CostSheet,cost_sheet_id)
    if not actor or not sheet: return RedirectResponse("/crm/advanced/quotations", status_code=303)
    valid = datetime.fromisoformat(valid_until) if valid_until else None
    db.add(PropertyQuotation(cost_sheet_id=cost_sheet_id, quotation_no=quotation_no.strip(), lead_id=lead_id, customer_id=customer_id, unit_id=unit_id, total_amount=sheet.total_amount, valid_until=valid, notes=notes.strip() or None, created_by_id=actor.id)); db.commit()
    return RedirectResponse("/crm/advanced/quotations", status_code=303)
