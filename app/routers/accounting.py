from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from io import BytesIO
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.accounting_models import AccountCategory, AccountingEntry, AccountingPeriod
from app.csrf import csrf_token, require_csrf
from app.database import get_db

router = APIRouter(tags=["accounting"])

CATEGORIES = [
    ("OFFICE_ELECTRICITY", "Office Electricity / Light Bill", "EXPENSE"),
    ("OFFICE_MAINTENANCE", "Office Maintenance & Repairs", "EXPENSE"),
    ("OFFICE_RENT", "Office Rent", "EXPENSE"),
    ("LOAN_EMI", "Business Loan EMI", "EXPENSE"),
    ("BANK_INTEREST", "Loan / Bank Interest", "EXPENSE"),
    ("STAFF_SALARY", "Staff Salaries", "EXPENSE"),
    ("STAFF_TRAINING", "Staff Training & Development", "EXPENSE"),
    ("MEALS_REFRESHMENTS", "Tea / Snacks / Lunch / Dinner", "EXPENSE"),
    ("OFFICE_SUPPLIES", "Stationery & Office Supplies", "EXPENSE"),
    ("TRAVEL_CONVEYANCE", "Travel & Conveyance", "EXPENSE"),
    ("TELEPHONE_INTERNET", "Telephone / Internet", "EXPENSE"),
    ("SOFTWARE_SUBSCRIPTIONS", "Software / SaaS Subscriptions", "EXPENSE"),
    ("ADVERTISING", "Advertising & Lead Generation", "EXPENSE"),
    ("MAGICBRICKS", "MagicBricks Lead Generation", "EXPENSE"),
    ("NINETY_NINE_ACRES", "99acres Lead Generation", "EXPENSE"),
    ("META_ADS", "Facebook / Meta Ads", "EXPENSE"),
    ("GOOGLE_ADS", "Google Ads / Lead Generation", "EXPENSE"),
    ("PROPERTY_PORTALS", "Other Property Portals", "EXPENSE"),
    ("CLIENT_MEETING", "Client Meeting / Hospitality", "EXPENSE"),
    ("PROFESSIONAL_FEES", "Professional / Consultancy Fees", "EXPENSE"),
    ("BANK_CHARGES", "Bank Charges", "EXPENSE"),
    ("TAXES_DUTIES", "Taxes / Government Charges", "EXPENSE"),
    ("OTHER_OPERATING", "Other Operating Expense", "EXPENSE"),
    ("SALES_REVENUE", "Sales / Brokerage / Commission Revenue", "INCOME"),
    ("COMMISSION_RECEIVED", "Commission Received", "INCOME"),
    ("OTHER_INCOME", "Other Income", "INCOME"),
    ("CASH", "Cash", "ASSET"),
    ("BANK", "Bank Account", "ASSET"),
    ("LOAN_LIABILITY", "Business Loan Liability", "LIABILITY"),
    ("OWNER_CAPITAL", "Owner Capital", "EQUITY"),
]


def actor(request: Request, db: Session):
    from app.main import _current_user
    user = _current_user(request, db)
    return user if user and user.role in {"ADMIN", "SUPER_ADMIN"} else None


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | {escape(title)}</title><style>body{{font-family:Arial;background:#f5f7fb;color:#10213f;padding:24px}}.wrap{{max-width:1250px;margin:auto}}.card{{background:#fff;padding:20px;border:1px solid #e5eaf2;border-radius:15px;margin-bottom:18px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.stat{{border:1px solid #e5eaf2;border-radius:10px;padding:14px}}.value{{font-size:22px;font-weight:800;margin-top:5px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}label{{display:block;font-size:12px;font-weight:700;margin:8px 0 4px}}input,select,textarea{{width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px}}.btn{{display:inline-block;border:0;border-radius:8px;padding:9px 13px;background:#2563eb;color:#fff;font-weight:700;text-decoration:none;cursor:pointer;margin-top:10px}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{padding:9px;border-bottom:1px solid #eef2f7;text-align:left}}th{{background:#f8fafc}}.muted{{color:#64748b;font-size:12px}}@media(max-width:800px){{.grid,.two{{grid-template-columns:1fr}}}}</style></head><body><div class='wrap'><h1>{escape(title)}</h1>{body}</div></body></html>")


def ensure_categories(db: Session):
    existing = {x.code for x in db.scalars(select(AccountCategory)).all()}
    changed = False
    for code, name, typ in CATEGORIES:
        if code not in existing:
            db.add(AccountCategory(code=code, name=name, account_type=typ, is_system=True)); changed = True
    if changed: db.commit()


def parse_date(value: str):
    return datetime.fromisoformat(value).replace(tzinfo=None)


@router.get("/accounting", response_class=HTMLResponse)
def accounting_page(request: Request, db: Session = Depends(get_db), from_date: str = "", to_date: str = ""):
    user = actor(request, db)
    if not user: return RedirectResponse("/dashboard", status_code=303)
    ensure_categories(db)
    entries = select(AccountingEntry).order_by(AccountingEntry.entry_date.desc(), AccountingEntry.id.desc())
    if from_date: entries = entries.where(AccountingEntry.entry_date >= parse_date(from_date))
    if to_date: entries = entries.where(AccountingEntry.entry_date < parse_date(to_date) .replace(hour=23, minute=59, second=59))
    rows = db.scalars(entries.limit(300)).all()
    income = sum((x.amount for x in rows if x.entry_type == "INCOME"), Decimal("0"))
    expenses = sum((x.amount for x in rows if x.entry_type == "EXPENSE"), Decimal("0"))
    gst = sum((x.gst_amount for x in rows), Decimal("0"))
    csrf = csrf_token(request)
    options = "".join(f"<option value='{code}'>{escape(name)}</option>" for code,name,typ in CATEGORIES if typ == "EXPENSE")
    body = "<div class='card'><p class='muted'>Admin + Super Admin only. Record every business expense, income, tax component and payment reference here. Category mapping is preconfigured for accounts-friendly reporting.</p><div class='grid'>" + "".join(f"<div class='stat'><div class='muted'>{k}</div><div class='value'>₹ {float(v):,.2f}</div></div>" for k,v in [("Income",income),("Expenses",expenses),("Operating Result",income-expenses),("GST captured",gst)]) + "</div></div>"
    body += f"<div class='card'><h2>New Accounting Entry</h2><form method='post' action='/accounting/entries'><input type='hidden' name='csrf_token' value='{csrf}'><div class='two'><div><label>Date</label><input type='date' name='entry_date' required></div><div><label>Type</label><select name='entry_type'><option>EXPENSE</option><option>INCOME</option></select></div><div><label>Category</label><select name='category_code'>{options}<option value='SALES_REVENUE'>Sales / Brokerage / Commission Revenue</option><option value='COMMISSION_RECEIVED'>Commission Received</option><option value='OTHER_INCOME'>Other Income</option></select></div><div><label>Amount (before GST)</label><input type='number' name='amount' min='0' step='0.01' required></div><div><label>GST Rate %</label><input type='number' name='gst_rate' min='0' max='100' step='0.01' value='0'></div><div><label>GST Amount</label><input type='number' name='gst_amount' min='0' step='0.01' value='0'></div><div><label>TDS Amount</label><input type='number' name='tds_amount' min='0' step='0.01' value='0'></div><div><label>Payment Mode</label><select name='payment_mode'><option>Bank</option><option>Cash</option><option>UPI</option><option>Card</option><option>Cheque</option><option>Credit</option></select></div><div><label>Party / Vendor / Customer</label><input name='party_name'></div><div><label>Invoice No.</label><input name='invoice_no'></div><div><label>Reference No.</label><input name='reference_no'></div><div><label>Bank / Account</label><input name='bank_account'></div></div><label>Description</label><textarea name='description' required></textarea><label>Notes</label><textarea name='notes'></textarea><button class='btn' type='submit'>Save Entry</button></form></div>"
    body += f"<div class='card'><h2>Ledger</h2><form class='two' method='get'><div><label>From</label><input type='date' name='from_date' value='{escape(from_date)}'></div><div><label>To</label><input type='date' name='to_date' value='{escape(to_date)}'></div><button class='btn' type='submit'>Filter</button><a class='btn' href='/accounting/export?from_date={escape(from_date)}&to_date={escape(to_date)}'>Export Excel</a></form><table><tr><th>Date</th><th>Type</th><th>Category</th><th>Description</th><th>Party</th><th>Amount</th><th>GST</th><th>Mode</th><th>Invoice</th></tr>" + "".join(f"<tr><td>{x.entry_date.date()}</td><td>{escape(x.entry_type)}</td><td>{escape(x.category_code)}</td><td>{escape(x.description)}</td><td>{escape(x.party_name or '—')}</td><td>₹ {float(x.amount):,.2f}</td><td>₹ {float(x.gst_amount):,.2f}</td><td>{escape(x.payment_mode or '—')}</td><td>{escape(x.invoice_no or '—')}</td></tr>" for x in rows) + "</table></div>"
    body += "<div class='card'><h2>Accounting Controls</h2><ul><li>Monthly / quarterly / yearly and custom-date P&amp;L can be generated from the same ledger.</li><li>GST amount, TDS, invoice and payment references are retained for reconciliation.</li><li>Vendor-wise and category-wise expense analysis is supported by the ledger fields.</li><li>Loan EMI can be recorded, while interest and principal should be separately reconciled in final books.</li><li>Every entry is attributable to the Admin/Super Admin who created it.</li></ul></div>"
    return page("Accounting & Finance", body)


@router.post("/accounting/entries", dependencies=[Depends(require_csrf)])
def create_entry(request: Request, entry_date: str = Form(...), entry_type: str = Form(...), category_code: str = Form(...), amount: Decimal = Form(...), gst_rate: Decimal = Form(0), gst_amount: Decimal = Form(0), tds_amount: Decimal = Form(0), payment_mode: str = Form(""), party_name: str = Form(""), invoice_no: str = Form(""), reference_no: str = Form(""), bank_account: str = Form(""), description: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user: return RedirectResponse("/dashboard", status_code=303)
    ensure_categories(db)
    category = db.scalar(select(AccountCategory).where(AccountCategory.code == category_code))
    if not category or entry_type not in {"EXPENSE", "INCOME"} or amount < 0 or gst_rate < 0 or gst_rate > 100 or gst_amount < 0 or tds_amount < 0:
        return RedirectResponse("/accounting?error=validation", status_code=303)
    db.add(AccountingEntry(entry_date=parse_date(entry_date), entry_type=entry_type, category_code=category_code, description=description.strip(), amount=amount, gst_rate=gst_rate, gst_amount=gst_amount, tds_amount=tds_amount, payment_mode=payment_mode.strip() or None, party_name=party_name.strip() or None, invoice_no=invoice_no.strip() or None, reference_no=reference_no.strip() or None, bank_account=bank_account.strip() or None, notes=notes.strip() or None, created_by_id=user.id))
    from app.main import _audit
    _audit(db, user.id, "ACCOUNTING_ENTRY_CREATED", None, {"category": category_code, "type": entry_type, "amount": str(amount)})
    db.commit()
    return RedirectResponse("/accounting", status_code=303)


@router.get("/accounting/export")
def export_accounting(request: Request, from_date: str = "", to_date: str = "", db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user: return RedirectResponse("/dashboard", status_code=303)
    q = select(AccountingEntry).order_by(AccountingEntry.entry_date.asc(), AccountingEntry.id.asc())
    if from_date: q = q.where(AccountingEntry.entry_date >= parse_date(from_date))
    if to_date: q = q.where(AccountingEntry.entry_date <= parse_date(to_date).replace(hour=23, minute=59, second=59))
    rows = db.scalars(q).all()
    wb = Workbook(); ws = wb.active; ws.title = "Ledger"
    headers = ["Date","Type","Category","Description","Party","Amount","GST Rate","GST Amount","TDS","Payment Mode","Invoice No","Reference No","Bank Account","Notes"]
    ws.append(headers)
    for x in rows: ws.append([x.entry_date.date(),x.entry_type,x.category_code,x.description,x.party_name,x.amount,x.gst_rate,x.gst_amount,x.tds_amount,x.payment_mode,x.invoice_no,x.reference_no,x.bank_account,x.notes])
    for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = min(max(max((len(str(c.value or "")) for c in col), default=10)+2,10),40)
    bio=BytesIO(); wb.save(bio); bio.seek(0)
    return StreamingResponse(bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":"attachment; filename=MetroCRM_Accounting_Ledger.xlsx"})
