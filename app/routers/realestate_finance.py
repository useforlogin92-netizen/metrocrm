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
from app.models import Unit
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
