from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from io import BytesIO

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting_logic import post_transaction
from app.accounting_models import AccountCategory, AccountingEntry, AccountingPeriod, JournalEntry, JournalLine
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
    ("VENDOR_PAYABLE", "Vendor / Supplier Payable", "LIABILITY"),
    ("CUSTOMER_RECEIVABLE", "Customer / Client Receivable", "ASSET"),
    ("LOAN_LIABILITY", "Business Loan Liability", "LIABILITY"),
    ("OWNER_CAPITAL", "Owner Capital", "EQUITY"),
    ("INPUT_CGST", "Input CGST", "ASSET"),
    ("INPUT_SGST", "Input SGST", "ASSET"),
    ("INPUT_IGST", "Input IGST", "ASSET"),
    ("OUTPUT_CGST", "Output CGST", "LIABILITY"),
    ("OUTPUT_SGST", "Output SGST", "LIABILITY"),
    ("OUTPUT_IGST", "Output IGST", "LIABILITY"),
    ("TDS_PAYABLE", "TDS Payable", "LIABILITY"),
]


def actor(request: Request, db: Session):
    from app.main import _current_user
    user = _current_user(request, db)
    return user if user and user.role in {"ADMIN", "SUPER_ADMIN"} else None


def page(title: str, body: str) -> HTMLResponse:
    css = "body{font-family:Arial;background:#f5f7fb;color:#10213f;padding:24px}.wrap{max-width:1250px;margin:auto}.card{background:#fff;padding:20px;border:1px solid #e5eaf2;border-radius:15px;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.stat{border:1px solid #e5eaf2;border-radius:10px;padding:14px}.value{font-size:22px;font-weight:800;margin-top:5px}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;font-size:12px;font-weight:700;margin:8px 0 4px}input,select,textarea{width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px}.btn{display:inline-block;border:0;border-radius:8px;padding:9px 13px;background:#2563eb;color:#fff;font-weight:700;text-decoration:none;cursor:pointer;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:9px;border-bottom:1px solid #eef2f7;text-align:left}th{background:#f8fafc}.muted{color:#64748b;font-size:12px}@media(max-width:800px){.grid,.two{grid-template-columns:1fr}}"
    return HTMLResponse(f"<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | {escape(title)}</title><style>{css}</style></head><body><div class='wrap'><h1>{escape(title)}</h1>{body}</div></body></html>")


def ensure_categories(db: Session):
    existing = {x.code for x in db.scalars(select(AccountCategory)).all()}
    changed = False
    for code, name, typ in CATEGORIES:
        if code not in existing:
            db.add(AccountCategory(code=code, name=name, account_type=typ, is_system=True))
            changed = True
    if changed:
        db.commit()


def dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def period_is_closed(db: Session, entry_date: datetime) -> bool:
    return db.scalar(
        select(AccountingPeriod.id).where(
            AccountingPeriod.status == "CLOSED",
            AccountingPeriod.from_date <= entry_date,
            AccountingPeriod.to_date >= entry_date,
        )
    ) is not None


def next_auto_entry_no(db: Session, prefix: str = "AUTO") -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    candidate = f"{prefix}-{stamp}"
    while db.scalar(select(JournalEntry.id).where(JournalEntry.entry_no == candidate)):
        candidate += "X"
    return candidate


@router.get("/accounting", response_class=HTMLResponse)
def accounting_page(request: Request, db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user:
        return RedirectResponse("/dashboard", status_code=303)
    ensure_categories(db)
    rows = db.scalars(select(AccountingEntry).order_by(AccountingEntry.entry_date.desc(), AccountingEntry.id.desc()).limit(300)).all()
    income = sum((dec(x.amount) for x in rows if x.entry_type == "INCOME"), Decimal(0))
    expenses = sum((dec(x.amount) for x in rows if x.entry_type == "EXPENSE"), Decimal(0))
    gst = sum((dec(x.gst_amount) for x in rows), Decimal(0))
    csrf = csrf_token(request)
    expense_opts = "".join(f"<option value='{c}'>{escape(n)}</option>" for c, n, t in CATEGORIES if t == "EXPENSE")
    income_opts = "".join(f"<option value='{c}'>{escape(n)}</option>" for c, n, t in CATEGORIES if t == "INCOME")
    body = "<div class='card'><p class='muted'>Restricted to Admin and Super Admin. Register entries are automatically posted to the double-entry journal.</p><div class='grid'>"
    body += "".join(f"<div class='stat'><div class='muted'>{k}</div><div class='value'>₹ {float(v):,.2f}</div></div>" for k, v in [("Income", income), ("Expenses", expenses), ("Net Operating Result", income - expenses), ("GST Captured", gst)])
    body += "</div></div>"
    body += f"<div class='card'><h2>Expense / Income Register</h2><form method='post' action='/accounting/entries'><input type='hidden' name='csrf_token' value='{csrf}'><div class='two'><div><label>Date</label><input type='date' name='entry_date' required></div><div><label>Type</label><select name='entry_type'><option>EXPENSE</option><option>INCOME</option></select></div><div><label>Category</label><select name='category_code'>{expense_opts}{income_opts}</select></div><div><label>Amount before GST</label><input name='amount' type='number' min='0' step='0.01' required></div><div><label>GST Rate %</label><input name='gst_rate' type='number' min='0' max='100' step='0.01' value='0'></div><div><label>GST Amount</label><input name='gst_amount' type='number' min='0' step='0.01' value='0'></div><div><label>TDS Amount</label><input name='tds_amount' type='number' min='0' step='0.01' value='0'></div><div><label>Payment Mode</label><select name='payment_mode'><option>Bank</option><option>Cash</option><option>UPI</option><option>Card</option><option>Cheque</option><option>Credit</option></select></div><div><label>Vendor / Party</label><input name='party_name'></div><div><label>Invoice No.</label><input name='invoice_no'></div><div><label>Reference No.</label><input name='reference_no'></div><div><label>Bank / Account</label><input name='bank_account'></div></div><label>Description</label><textarea name='description' required></textarea><label>Notes</label><textarea name='notes'></textarea><button class='btn' type='submit'>Save & Post Transaction</button></form></div>"
    body += "<div class='card'><h2>Ledger</h2><table><tr><th>Date</th><th>Type</th><th>Category</th><th>Description</th><th>Party</th><th>Amount</th><th>GST</th><th>TDS</th><th>Mode</th><th>Invoice</th></tr>"
    body += "".join(f"<tr><td>{x.entry_date.date()}</td><td>{x.entry_type}</td><td>{escape(x.category_code)}</td><td>{escape(x.description)}</td><td>{escape(x.party_name or '—')}</td><td>₹ {float(x.amount):,.2f}</td><td>₹ {float(x.gst_amount):,.2f}</td><td>₹ {float(x.tds_amount):,.2f}</td><td>{escape(x.payment_mode or '—')}</td><td>{escape(x.invoice_no or '—')}</td></tr>" for x in rows)
    body += "</table><a class='btn' href='/accounting/export'>Export Full Ledger Excel</a></div>"
    body += "<div class='card'><h2>Finance Controls</h2><a class='btn' href='/accounting/journal'>Journal</a> <a class='btn' href='/accounting/financials'>Financial Statements</a> <a class='btn' href='/accounting/periods'>Accounting Periods</a></div>"
    return page("Accounting & Finance", body)


@router.post("/accounting/entries", dependencies=[Depends(require_csrf)])
def create_entry(request: Request, entry_date: str = Form(...), entry_type: str = Form(...), category_code: str = Form(...), amount: Decimal = Form(...), gst_rate: Decimal = Form(0), gst_amount: Decimal = Form(0), tds_amount: Decimal = Form(0), payment_mode: str = Form(""), party_name: str = Form(""), invoice_no: str = Form(""), reference_no: str = Form(""), bank_account: str = Form(""), description: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db)):
    user = actor(request, db)
    ensure_categories(db)
    category = db.scalar(select(AccountCategory).where(AccountCategory.code == category_code))
    try:
        parsed_date = dt(entry_date)
    except ValueError:
        return RedirectResponse("/accounting?error=date", status_code=303)
    if not user or not category or category.account_type not in {"EXPENSE", "INCOME"} or entry_type not in {"EXPENSE", "INCOME"} or category.account_type != entry_type or amount < 0 or gst_rate < 0 or gst_rate > 100 or gst_amount < 0 or tds_amount < 0:
        return RedirectResponse("/accounting?error=validation", status_code=303)
    if period_is_closed(db, parsed_date):
        return RedirectResponse("/accounting?error=period-closed", status_code=303)
    entry = AccountingEntry(entry_date=parsed_date, entry_type=entry_type, category_code=category_code, description=description.strip(), amount=amount, gst_rate=gst_rate, gst_amount=gst_amount, tds_amount=tds_amount, payment_mode=payment_mode.strip() or None, party_name=party_name.strip() or None, invoice_no=invoice_no.strip() or None, reference_no=reference_no.strip() or None, bank_account=bank_account.strip() or None, notes=notes.strip() or None, created_by_id=user.id)
    db.add(entry)
    db.flush()
    try:
        post_transaction(db, entry, user.id, next_auto_entry_no(db))
        from app.main import _audit
        _audit(db, user.id, "ACCOUNTING_ENTRY_POSTED", None, {"category": category_code, "type": entry_type, "amount": str(amount)})
        db.commit()
    except ValueError:
        db.rollback()
        return RedirectResponse("/accounting?error=posting", status_code=303)
    return RedirectResponse("/accounting", status_code=303)


@router.get("/accounting/journal", response_class=HTMLResponse)
def journal_page(request: Request, db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user:
        return RedirectResponse("/dashboard", status_code=303)
    ensure_categories(db)
    accounts = db.scalars(select(AccountCategory).order_by(AccountCategory.account_type, AccountCategory.code)).all()
    rows = db.scalars(select(JournalEntry).order_by(JournalEntry.entry_date.desc()).limit(100)).all()
    csrf = csrf_token(request)
    opts = "".join(f"<option value='{a.code}'>{a.code} — {escape(a.name)}</option>" for a in accounts)
    body = f"<div class='card'><h2>Balanced Journal Entry</h2><p class='muted'>Manual journals are available to Admin/Super Admin for controlled adjustments. Posted entries cannot be edited here.</p><form method='post' action='/accounting/journal'><input type='hidden' name='csrf_token' value='{csrf}'><div class='two'><div><label>Date</label><input type='date' name='entry_date' required></div><div><label>Entry No.</label><input name='entry_no' required></div><div><label>Debit Account</label><select name='debit_account'>{opts}</select></div><div><label>Credit Account</label><select name='credit_account'>{opts}</select></div><div><label>Amount</label><input name='amount' type='number' min='0.01' step='0.01' required></div><div><label>Reference</label><input name='reference_no'></div></div><label>Narration</label><textarea name='narration' required></textarea><button class='btn' type='submit'>Post Balanced Journal</button></form></div><div class='card'><h2>Recent Journals</h2><table><tr><th>No.</th><th>Date</th><th>Narration</th><th>Status</th></tr>" + "".join(f"<tr><td>{escape(x.entry_no)}</td><td>{x.entry_date.date()}</td><td>{escape(x.narration)}</td><td>{escape(x.status)}</td></tr>" for x in rows) + "</table></div>"
    return page("Journal", body)


@router.post("/accounting/journal", dependencies=[Depends(require_csrf)])
def post_journal(request: Request, entry_date: str = Form(...), entry_no: str = Form(...), debit_account: str = Form(...), credit_account: str = Form(...), amount: Decimal = Form(...), reference_no: str = Form(""), narration: str = Form(...), db: Session = Depends(get_db)):
    user = actor(request, db)
    ensure_categories(db)
    try:
        parsed_date = dt(entry_date)
    except ValueError:
        return RedirectResponse("/accounting/journal?error=date", status_code=303)
    if not user or amount <= 0 or debit_account == credit_account:
        return RedirectResponse("/accounting/journal?error=validation", status_code=303)
    if not db.scalar(select(AccountCategory.id).where(AccountCategory.code == debit_account)) or not db.scalar(select(AccountCategory.id).where(AccountCategory.code == credit_account)):
        return RedirectResponse("/accounting/journal?error=validation", status_code=303)
    if period_is_closed(db, parsed_date):
        return RedirectResponse("/accounting/journal?error=period-closed", status_code=303)
    clean_no = entry_no.strip()
    if not clean_no or db.scalar(select(JournalEntry.id).where(JournalEntry.entry_no == clean_no)):
        return RedirectResponse("/accounting/journal?error=duplicate", status_code=303)
    je = JournalEntry(entry_no=clean_no, entry_date=parsed_date, narration=narration.strip(), reference_no=reference_no.strip() or None, created_by_id=user.id, status="POSTED")
    db.add(je)
    db.flush()
    db.add_all([JournalLine(journal_entry_id=je.id, account_code=debit_account, debit=amount, credit=0), JournalLine(journal_entry_id=je.id, account_code=credit_account, debit=0, credit=amount)])
    from app.main import _audit
    _audit(db, user.id, "ACCOUNTING_MANUAL_JOURNAL_POSTED", None, {"entry_no": clean_no, "amount": str(amount)})
    db.commit()
    return RedirectResponse("/accounting/journal", status_code=303)


@router.get("/accounting/financials", response_class=HTMLResponse)
def financials(request: Request, db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user:
        return RedirectResponse("/dashboard", status_code=303)
    ensure_categories(db)
    accounts = db.scalars(select(AccountCategory).order_by(AccountCategory.account_type, AccountCategory.code)).all()
    lines = db.scalars(select(JournalLine)).all()
    balances: dict[str, Decimal] = {}
    for line in lines:
        balances[line.account_code] = balances.get(line.account_code, Decimal(0)) + dec(line.debit) - dec(line.credit)
    income = sum((-balances.get(a.code, Decimal(0)) for a in accounts if a.account_type == "INCOME"), Decimal(0))
    expense = sum((balances.get(a.code, Decimal(0)) for a in accounts if a.account_type == "EXPENSE"), Decimal(0))
    profit = income - expense
    assets = sum((balances.get(a.code, Decimal(0)) for a in accounts if a.account_type == "ASSET"), Decimal(0))
    liabilities = sum((-balances.get(a.code, Decimal(0)) for a in accounts if a.account_type == "LIABILITY"), Decimal(0))
    equity = sum((-balances.get(a.code, Decimal(0)) for a in accounts if a.account_type == "EQUITY"), Decimal(0)) + profit
    total_debit = sum((dec(x.debit) for x in lines), Decimal(0))
    total_credit = sum((dec(x.credit) for x in lines), Decimal(0))
    diff = total_debit - total_credit
    body = f"<div class='grid'><div class='stat'><div class='muted'>Income</div><div class='value'>₹ {float(income):,.2f}</div></div><div class='stat'><div class='muted'>Expenses</div><div class='value'>₹ {float(expense):,.2f}</div></div><div class='stat'><div class='muted'>Net Profit / Loss</div><div class='value'>₹ {float(profit):,.2f}</div></div><div class='stat'><div class='muted'>Trial Balance Difference</div><div class='value'>₹ {float(diff):,.2f}</div></div></div><div class='card'><h2>Profit & Loss</h2><p>Income: ₹ {float(income):,.2f} &nbsp; | &nbsp; Expenses: ₹ {float(expense):,.2f} &nbsp; | &nbsp; Net: ₹ {float(profit):,.2f}</p></div><div class='card'><h2>Balance Sheet Foundation</h2><p>Assets: ₹ {float(assets):,.2f} &nbsp; | &nbsp; Liabilities: ₹ {float(liabilities):,.2f} &nbsp; | &nbsp; Equity incl. current result: ₹ {float(equity):,.2f}</p><p class='muted'>Management accounting foundation; reconcile with final statutory books and CA review before GST/ITR filing.</p></div><div class='card'><h2>Trial Balance / Ledger Balances</h2><table><tr><th>Code</th><th>Account</th><th>Type</th><th>Debit − Credit</th></tr>" + "".join(f"<tr><td>{escape(a.code)}</td><td>{escape(a.name)}</td><td>{escape(a.account_type)}</td><td>₹ {float(balances.get(a.code, Decimal(0))):,.2f}</td></tr>" for a in accounts) + "</table></div>"
    return page("Financial Statements", body)


@router.get("/accounting/periods", response_class=HTMLResponse)
def periods_page(request: Request, db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user:
        return RedirectResponse("/dashboard", status_code=303)
    rows = db.scalars(select(AccountingPeriod).order_by(AccountingPeriod.from_date.desc())).all()
    csrf = csrf_token(request)
    body = f"<div class='card'><h2>Accounting Period</h2><form method='post' action='/accounting/periods'><input type='hidden' name='csrf_token' value='{csrf}'><div class='two'><div><label>Name</label><input name='period_name' placeholder='FY 2026-27' required></div><div><label>From</label><input type='date' name='from_date' required></div><div><label>To</label><input type='date' name='to_date' required></div></div><button class='btn' type='submit'>Create Open Period</button></form></div><div class='card'><h2>Periods</h2><table><tr><th>Name</th><th>From</th><th>To</th><th>Status</th><th>Action</th></tr>" + "".join(f"<tr><td>{escape(x.period_name)}</td><td>{x.from_date.date()}</td><td>{x.to_date.date()}</td><td>{escape(x.status)}</td><td>" + (f"<form method='post' action='/accounting/periods/{x.id}/close' style='display:inline'><input type='hidden' name='csrf_token' value='{csrf}'><button class='btn' type='submit'>Close Period</button></form>" if x.status != "CLOSED" else "Locked") + "</td></tr>" for x in rows) + "</table></div>"
    return page("Accounting Periods", body)


@router.post("/accounting/periods", dependencies=[Depends(require_csrf)])
def create_period(request: Request, period_name: str = Form(...), from_date: str = Form(...), to_date: str = Form(...), db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user:
        return RedirectResponse("/dashboard", status_code=303)
    try:
        start, end = dt(from_date), dt(to_date)
    except ValueError:
        return RedirectResponse("/accounting/periods?error=date", status_code=303)
    if start > end or not period_name.strip() or db.scalar(select(AccountingPeriod.id).where(AccountingPeriod.period_name == period_name.strip())):
        return RedirectResponse("/accounting/periods?error=validation", status_code=303)
    db.add(AccountingPeriod(period_name=period_name.strip(), from_date=start, to_date=end, status="OPEN"))
    db.commit()
    return RedirectResponse("/accounting/periods", status_code=303)


@router.post("/accounting/periods/{period_id}/close", dependencies=[Depends(require_csrf)])
def close_period(period_id: int, request: Request, db: Session = Depends(get_db)):
    user = actor(request, db)
    period = db.get(AccountingPeriod, period_id)
    if not user or not period or period.status == "CLOSED":
        return RedirectResponse("/accounting/periods?error=validation", status_code=303)
    period.status = "CLOSED"
    period.closed_by_id = user.id
    period.closed_at = datetime.utcnow()
    from app.main import _audit
    _audit(db, user.id, "ACCOUNTING_PERIOD_CLOSED", None, {"period_id": period.id, "period_name": period.period_name})
    db.commit()
    return RedirectResponse("/accounting/periods", status_code=303)


@router.get("/accounting/export")
def export_accounting(request: Request, db: Session = Depends(get_db)):
    user = actor(request, db)
    if not user:
        return RedirectResponse("/dashboard", status_code=303)
    rows = db.scalars(select(AccountingEntry).order_by(AccountingEntry.entry_date.asc(), AccountingEntry.id.asc())).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Ledger"
    ws.append(["Date", "Type", "Category", "Description", "Party", "Amount", "GST Rate", "GST Amount", "TDS", "Payment Mode", "Invoice No", "Reference No", "Bank Account", "Notes"])
    for x in rows:
        ws.append([x.entry_date.date(), x.entry_type, x.category_code, x.description, x.party_name, x.amount, x.gst_rate, x.gst_amount, x.tds_amount, x.payment_mode, x.invoice_no, x.reference_no, x.bank_account, x.notes])
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=MetroCRM_Accounting_Ledger.xlsx"})
