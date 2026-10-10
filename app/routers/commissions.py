from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Booking, Commission, Customer, Developer, Project, User

router = APIRouter(tags=["commission-tracking"])

COMMISSION_VIEW_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE"}
COMMISSION_MANAGE_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER"}
COMMISSION_RECEIVE_ROLES = {"SUPER_ADMIN", "ADMIN"}
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _scope_user_ids(actor: User, db: Session) -> set[int]:
    if actor.role in {"SUPER_ADMIN", "ADMIN"}:
        return set(db.scalars(select(User.id)).all())
    ids = {actor.id}
    if actor.role in {"MANAGER", "TL"}:
        frontier = {actor.id}
        while frontier:
            children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
            frontier = {int(uid) for uid in children if int(uid) not in ids}
            ids.update(frontier)
    return ids


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


def _visible_commissions(actor: User, db: Session) -> list[Commission]:
    query = select(Commission).outerjoin(Booking, Commission.booking_id == Booking.id)
    if actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        scope_ids = _scope_user_ids(actor, db)
        query = query.where(or_(
            Commission.employee_id.in_(scope_ids),
            Booking.employee_id.in_(scope_ids),
            Booking.manager_id.in_(scope_ids),
        ))
    return list(db.scalars(query.order_by(Commission.id.desc()).limit(300)).all())


def _visible_bookings(actor: User, db: Session) -> list[Booking]:
    query = select(Booking).order_by(Booking.booking_date.desc()).limit(500)
    if actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        scope_ids = _scope_user_ids(actor, db)
        query = select(Booking).where(
            or_(Booking.employee_id.in_(scope_ids), Booking.manager_id.in_(scope_ids))
        ).order_by(Booking.booking_date.desc()).limit(500)
    return list(db.scalars(query).all())


@router.get("/crm/advanced/commissions", response_class=HTMLResponse)
def commission_tracker(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in COMMISSION_VIEW_ROLES:
        return RedirectResponse("/dashboard", status_code=303)

    commissions = _visible_commissions(actor, db)
    bookings = _visible_bookings(actor, db) if actor.role in COMMISSION_MANAGE_ROLES else []
    customer_ids = {b.customer_id for b in bookings}
    customer_ids.update(
        b.customer_id for row in commissions
        if (b := db.get(Booking, row.booking_id)) is not None
    )
    customers = {
        item.id: item for item in db.scalars(
            select(Customer).where(Customer.id.in_(customer_ids))
        ).all()
    } if customer_ids else {}
    projects = {
        item.id: item for item in db.scalars(
            select(Project).where(Project.id.in_({
                row.project_id for row in commissions if row.project_id is not None
            } | {b.project_id for b in bookings if b.project_id is not None}))
        ).all()
    } if any(row.project_id is not None for row in commissions) or any(b.project_id is not None for b in bookings) else {}
    developer_ids = {p.developer_id for p in projects.values() if p.developer_id is not None}
    developers = {
        item.id: item for item in db.scalars(
            select(Developer).where(Developer.id.in_(developer_ids))
        ).all()
    } if developer_ids else {}
    employee_ids = {row.employee_id for row in commissions if row.employee_id is not None}
    employee_ids.update(b.employee_id for b in bookings if b.employee_id is not None)
    employees = {
        item.id: item for item in db.scalars(
            select(User).where(User.id.in_(employee_ids))
        ).all()
    } if employee_ids else {}

    total_payable = sum((_money(row.payable_amount if row.payable_amount is not None else row.amount) for row in commissions), ZERO)
    total_received = sum((_money(row.received_amount) for row in commissions), ZERO)
    total_pending = sum((_money(row.pending_amount if row.pending_amount is not None else _money(row.payable_amount if row.payable_amount is not None else row.amount) - _money(row.received_amount)) for row in commissions), ZERO)
    csrf = escape(csrf_token(request))

    form = ""
    if actor.role in COMMISSION_MANAGE_ROLES:
        options = []
        for booking in bookings:
            customer = customers.get(booking.customer_id)
            project = projects.get(booking.project_id)
            label = f"Booking #{booking.id} · {customer.name if customer else 'Customer not linked'} · {project.name if project else 'Project not linked'} · Sale value ₹{float(_money(booking.sale_value)):,.2f}"
            options.append(f'<option value="{booking.id}">{escape(label)}</option>')
        form = (
            "<section class='card'><h2>Record Expected Commission</h2>"
            "<p class='muted'>Choose a booking. If expected amount is blank, MetroCRM calculates it from booking sale value × commission percentage. "
            "Payment receipts are recorded separately and audited.</p>"
            "<form method='post' action='/crm/advanced/commissions' class='grid'>"
            f"<input type='hidden' name='csrf_token' value='{csrf}'>"
            "<label>Booking *<select name='booking_id' required><option value=''>Select a permitted booking</option>"
            + "".join(options) + "</select></label>"
            "<label>Commission % *<input name='commission_percent' type='number' min='0.0001' max='100' step='0.0001' required></label>"
            "<label>Expected amount (INR, optional)<input name='amount' type='number' min='0.01' step='0.01' placeholder='Auto-calculate from sale value'></label>"
            "<label>Payable amount (INR, optional)<input name='payable_amount' type='number' min='0' step='0.01' placeholder='Defaults to expected amount'></label>"
            "<label class='wide'>Remarks<input name='remarks' maxlength='2000' placeholder='Developer confirmation, invoice reference, agreed terms'></label>"
            "<button class='btn' type='submit'>Save Commission</button></form></section>"
        )

    rows = []
    for row in commissions:
        booking = db.get(Booking, row.booking_id) if row.booking_id else None
        customer = customers.get(booking.customer_id) if booking else None
        project = projects.get(row.project_id) if row.project_id else (projects.get(booking.project_id) if booking else None)
        developer = developers.get(row.developer_id) if row.developer_id else (developers.get(project.developer_id) if project else None)
        employee = employees.get(row.employee_id) if row.employee_id else (employees.get(booking.employee_id) if booking and booking.employee_id else None)
        payable = _money(row.payable_amount if row.payable_amount is not None else row.amount)
        received = _money(row.received_amount)
        pending = _money(row.pending_amount if row.pending_amount is not None else payable - received)
        status = "RECEIVED" if pending <= ZERO else ("PARTIALLY RECEIVED" if received > ZERO else "PENDING")
        receive_form = ""
        if actor.role in COMMISSION_RECEIVE_ROLES and pending > ZERO:
            receive_form = (
                f"<form method='post' action='/crm/advanced/commissions/{row.id}/receive'>"
                f"<input type='hidden' name='csrf_token' value='{csrf}'>"
                f"<input name='amount_received' type='number' min='0.01' max='{pending}' step='0.01' required placeholder='Amount received'>"
                "<button class='btn secondary' type='submit'>Record Receipt</button></form>"
            )
        rows.append(
            f"<tr><td>#{row.id}</td><td>{'#'+str(booking.id) if booking else '—'}<br>{escape(customer.name if customer else '—')}</td>"
            f"<td>{escape(project.name if project else '—')}<br>{escape(developer.name if developer else '—')}</td>"
            f"<td>{escape(employee.username if employee else 'Unassigned')}</td>"
            f"<td>{float(row.commission_percent or 0):.4f}%</td>"
            f"<td>₹{float(_money(row.amount)):,.2f}</td><td>₹{float(payable):,.2f}</td>"
            f"<td>₹{float(received):,.2f}</td><td>₹{float(pending):,.2f}</td>"
            f"<td>{status}<br>{row.payment_date.strftime('%d %b %Y') if row.payment_date else 'No receipt date'}</td>"
            f"<td>{escape(row.remarks or '—')} {receive_form}</td></tr>"
        )
    body = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>MetroCRM | Commission Tracking</title><style>body{font:14px Arial,sans-serif;background:#f4f7fb;color:#17243a;margin:0;padding:24px}"
        "main{max-width:1500px;margin:auto}.card{background:#fff;border:1px solid #e1e8f0;border-radius:14px;padding:20px;margin-bottom:18px}"
        ".grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}label{display:block;font-weight:700}input,select{display:block;width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd5e1;border-radius:8px;margin-top:5px}"
        ".wide{grid-column:1/-1}.btn{display:inline-block;background:#1d4ed8;color:#fff;border:0;border-radius:8px;padding:9px 12px;font-weight:700;cursor:pointer;margin-top:8px}.btn.secondary{background:#0f766e}"
        ".stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.stat{background:#f8fafc;padding:14px;border:1px solid #e2e8f0;border-radius:10px}.value{font-size:22px;font-weight:800;margin-top:5px}"
        ".tablewrap{overflow:auto}table{width:100%;min-width:1200px;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #e8edf4;text-align:left;vertical-align:top}th{background:#f8fafc}.muted{color:#64748b}"
        "@media(max-width:700px){.grid,.stats{grid-template-columns:1fr}}</style></head><body><main><h1>Commission Tracking</h1>"
        "<p class='muted'>Track expected, payable, received and pending developer commission against bookings. Sales staff see only their own commission records; managers see their reporting scope.</p>"
        "<div class='stats'><div class='stat'><div class='muted'>Total Payable</div><div class='value'>₹"
        + f"{float(total_payable):,.2f}</div></div><div class='stat'><div class='muted'>Total Received</div><div class='value'>₹"
        + f"{float(total_received):,.2f}</div></div><div class='stat'><div class='muted'>Pending</div><div class='value'>₹"
        + f"{float(total_pending):,.2f}</div></div></div>"
        + form
        + "<section class='card'><h2>Commission Register</h2><div class='tablewrap'><table><thead><tr><th>Record</th><th>Booking / Customer</th><th>Project / Developer</th><th>Sales Owner</th><th>Rate</th><th>Expected</th><th>Payable</th><th>Received</th><th>Pending</th><th>Status / Date</th><th>Remarks / Receipt</th></tr></thead><tbody>"
        + ("".join(rows) or "<tr><td colspan='11'>No commission records are available in your permitted scope.</td></tr>")
        + "</tbody></table></div></section><p><a href='/dashboard'>Dashboard</a> · <a href='/crm/advanced'>Advanced CRM Hub</a></p></main></body></html>"
    )
    return HTMLResponse(body)


@router.post("/crm/advanced/commissions", dependencies=[Depends(require_csrf)])
def create_commission(
    request: Request,
    booking_id: int = Form(...),
    commission_percent: Decimal = Form(...),
    amount: Decimal | None = Form(None),
    payable_amount: Decimal | None = Form(None),
    remarks: str = Form(""),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    if not actor or actor.role not in COMMISSION_MANAGE_ROLES:
        return RedirectResponse("/dashboard", status_code=303)
    booking = db.get(Booking, booking_id)
    if not booking:
        return HTMLResponse("Booking not found.", status_code=404)
    scope_ids = _scope_user_ids(actor, db)
    if actor.role not in {"SUPER_ADMIN", "ADMIN"} and booking.employee_id not in scope_ids and booking.manager_id not in scope_ids:
        return HTMLResponse("Booking is outside your permitted scope.", status_code=403)
    if commission_percent <= 0 or commission_percent > 100:
        return HTMLResponse("Commission percentage must be greater than 0 and no more than 100.", status_code=400)
    project = db.get(Project, booking.project_id) if booking.project_id else None
    gross = _money(amount) if amount is not None else (_money(booking.sale_value) * commission_percent / Decimal("100")).quantize(CENT)
    if gross <= ZERO:
        return HTMLResponse("Enter an expected amount or ensure the booking has a valid sale value.", status_code=400)
    payable = _money(payable_amount) if payable_amount is not None else gross
    if payable < ZERO or payable > gross:
        return HTMLResponse("Payable amount must be between zero and the expected commission amount.", status_code=400)
    duplicate = db.scalar(select(Commission).where(
        Commission.booking_id == booking.id,
        Commission.employee_id == booking.employee_id,
        Commission.developer_id == (project.developer_id if project else None),
    ))
    if duplicate:
        return HTMLResponse("A commission record already exists for this booking, sales owner, and developer.", status_code=409)
    record = Commission(
        developer_id=project.developer_id if project else None,
        project_id=booking.project_id,
        booking_id=booking.id,
        employee_id=booking.employee_id,
        commission_percent=commission_percent,
        amount=gross,
        payable_amount=payable,
        received_amount=ZERO,
        pending_amount=payable,
        remarks=remarks.strip() or None,
    )
    db.add(record)
    db.flush()
    db.add(AuditEvent(
        actor_user_id=actor.id, action="COMMISSION_RECORD_CREATED",
        entity_type="Commission", entity_id=str(record.id),
        details=json.dumps({"booking_id": booking.id, "commission_percent": str(commission_percent), "amount": str(gross), "payable_amount": str(payable)}),
    ))
    db.commit()
    return RedirectResponse("/crm/advanced/commissions", status_code=303)


@router.post("/crm/advanced/commissions/{commission_id}/receive", dependencies=[Depends(require_csrf)])
def receive_commission_payment(
    commission_id: int,
    request: Request,
    amount_received: Decimal = Form(...),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    if not actor or actor.role not in COMMISSION_RECEIVE_ROLES:
        return RedirectResponse("/dashboard", status_code=303)
    record = db.get(Commission, commission_id)
    if not record:
        return HTMLResponse("Commission record not found.", status_code=404)
    payable = _money(record.payable_amount if record.payable_amount is not None else record.amount)
    received = _money(record.received_amount)
    pending = _money(record.pending_amount if record.pending_amount is not None else payable - received)
    if amount_received <= ZERO:
        return HTMLResponse("Receipt amount must be greater than zero.", status_code=400)
    if amount_received > pending:
        return HTMLResponse("Receipt amount cannot exceed the pending commission balance.", status_code=400)
    received += _money(amount_received)
    pending -= _money(amount_received)
    record.received_amount = received
    record.pending_amount = pending
    record.payment_date = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditEvent(
        actor_user_id=actor.id, action="COMMISSION_PAYMENT_RECEIVED",
        entity_type="Commission", entity_id=str(record.id),
        details=json.dumps({"received_now": str(_money(amount_received)), "total_received": str(received), "pending_amount": str(pending)}),
    ))
    db.commit()
    return RedirectResponse("/crm/advanced/commissions", status_code=303)
