from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import Booking, Customer, Lead, User
from app.crm_plus_models import (
    ChannelPartner, CRMTask, LeadScore, MarketingCampaign, PaymentMilestone,
    PossessionChecklist, SalesTarget, ServiceTicket,
)

router = APIRouter(tags=["crm-plus"])


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def current_user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def team_ids(actor: User, db: Session) -> set[int]:
    if actor.role in {"SUPER_ADMIN", "ADMIN"}:
        return set(db.scalars(select(User.id)).all())
    ids = {actor.id}
    changed = True
    while changed:
        changed = False
        children = db.scalars(select(User).where(User.reporting_manager_id.in_(ids))).all()
        for child in children:
            if child.id not in ids:
                ids.add(child.id)
                changed = True
    return ids


def can_manage_team(actor: User, target_id: int, db: Session) -> bool:
    return target_id in team_ids(actor, db)


def customer_ids(actor: User, db: Session) -> set[int]:
    if actor.role in {"SUPER_ADMIN", "ADMIN"}:
        return set(db.scalars(select(Customer.id)).all())
    ids = team_ids(actor, db)
    lead_customer_ids = set(db.scalars(select(Lead.customer_id).where(Lead.assigned_user_id.in_(ids), Lead.customer_id.is_not(None))).all())
    booking_customer_ids = set(db.scalars(select(Booking.customer_id).where(or_(Booking.employee_id.in_(ids), Booking.manager_id.in_(ids)))).all())
    return {int(value) for value in lead_customer_ids | booking_customer_ids if value is not None}


def score_lead(lead: Lead) -> tuple[int, str, list[str]]:
    score = 0
    reasons = []
    source = (lead.source or "").upper()
    if source in {"WEBSITE", "WHATSAPP", "REFERRAL", "MAGICBRICKS", "99ACRES", "HOUSING"}:
        score += 20; reasons.append("high-intent source")
    elif source:
        score += 10; reasons.append("known source")
    if lead.customer_id:
        score += 15; reasons.append("linked customer")
    if lead.budget_min is not None or lead.budget_max is not None:
        score += 15; reasons.append("budget captured")
    if lead.preferred_location:
        score += 10; reasons.append("location captured")
    if lead.bhk or lead.property_type:
        score += 10; reasons.append("property preference captured")
    if lead.assigned_user_id:
        score += 10; reasons.append("owner assigned")
    age_days = (now() - lead.created_at).total_seconds() / 86400 if lead.created_at else 999
    if age_days <= 1:
        score += 20; reasons.append("fresh lead")
    elif age_days <= 7:
        score += 10; reasons.append("recent lead")
    score = min(100, score)
    grade = "A" if score >= 75 else "B" if score >= 50 else "C"
    return score, grade, reasons


def score_all(actor: User, db: Session) -> int:
    ids = team_ids(actor, db)
    leads = db.scalars(select(Lead).where(Lead.assigned_user_id.in_(ids))).all()
    count = 0
    for lead in leads:
        score, grade, reasons = score_lead(lead)
        row = db.scalar(select(LeadScore).where(LeadScore.lead_id == lead.id))
        if not row:
            row = LeadScore(lead_id=lead.id)
            db.add(row)
        row.score = score
        row.grade = grade
        row.reasons_json = json.dumps(reasons)
        row.calculated_at = now()
        count += 1
    db.commit()
    return count


def page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | {escape(title)}</title><style>body{{font-family:Inter,Arial,sans-serif;background:#f5f7fb;color:#10213f;margin:0;padding:24px}}.wrap{{max-width:1200px;margin:auto}}.card{{background:#fff;border:1px solid #e5eaf2;border-radius:16px;padding:20px;margin-bottom:18px;box-shadow:0 5px 20px #0000000a}}h1{{margin:0 0 5px}}h2{{font-size:18px}}.muted{{color:#64748b;font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.stat{{border:1px solid #e5eaf2;border-radius:12px;padding:14px}}.value{{font-size:24px;font-weight:800;margin-top:5px}}.row{{display:flex;gap:9px;align-items:center;flex-wrap:wrap}}.btn{{display:inline-block;background:#2563eb;color:#fff;text-decoration:none;border:0;border-radius:9px;padding:9px 13px;font-weight:700;cursor:pointer}}.btn.secondary{{background:#0f766e}}.btn.warn{{background:#b45309}}input,select,textarea{{padding:9px;border:1px solid #cbd5e1;border-radius:8px;width:100%;box-sizing:border-box}}label{{font-size:12px;font-weight:700;display:block;margin:9px 0 5px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid #eef2f7;text-align:left}}th{{background:#f8fafc}}.pill{{padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;background:#eff6ff;color:#1d4ed8}}@media(max-width:850px){{.grid,.two{{grid-template-columns:1fr 1fr}}}}@media(max-width:600px){{.grid,.two{{grid-template-columns:1fr}}}}</style></head><body><div class='wrap'><div class='row' style='justify-content:space-between;margin-bottom:18px'><div><h1>{escape(title)}</h1><div class='muted'>Advanced real-estate CRM operations</div></div><a class='btn secondary' href='/dashboard'>Dashboard</a></div>{body}</div></body></html>"""
    return HTMLResponse(html)


@router.get("/crm/advanced", response_class=HTMLResponse)
def advanced_hub(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    ids = team_ids(actor, db)
    lead_count = db.scalar(select(func.count(Lead.id)).where(Lead.assigned_user_id.in_(ids))) or 0
    source_rows = db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(Lead.assigned_user_id.in_(ids))
        .group_by(Lead.source)
        .order_by(func.count(Lead.id).desc())
    ).all()
    open_tasks = db.scalar(select(func.count(CRMTask.id)).where(CRMTask.assigned_user_id.in_(ids), CRMTask.status != "DONE")) or 0
    overdue_tasks = db.scalar(select(func.count(CRMTask.id)).where(CRMTask.assigned_user_id.in_(ids), CRMTask.status != "DONE", CRMTask.due_at < now())) or 0
    scoped_customer_ids = customer_ids(actor, db)
    open_tickets = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.customer_id.in_(scoped_customer_ids), ServiceTicket.status.not_in(["RESOLVED", "CLOSED"]))) if scoped_customer_ids else 0
    body = "<div class='card'><h2>Recommended CRM capabilities enabled</h2><p class='muted'>Lead intelligence, task discipline, targets, marketing attribution, channel partners and post-booking customer care.</p><div class='grid'>"
    for label, value in [("Scoped Leads", lead_count), ("Open Tasks", open_tasks), ("Overdue Tasks", overdue_tasks), ("Open Service Tickets", open_tickets or 0)]:
        body += f"<div class='stat'><div class='muted'>{label}</div><div class='value'>{value}</div></div>"
    body += "</div></div>"
    source_summary = "".join(
        f"<tr><td>{escape(str(source or 'UNSPECIFIED'))}</td><td>{count}</td></tr>"
        for source, count in source_rows
    ) or "<tr><td colspan='2'>No leads are currently visible in your assigned scope.</td></tr>"
    body += "<div class='card'><h2>Lead Operations</h2><p class='muted'>Manage real-estate enquiries, capture lead sources, and import leads using the standard Excel template.</p><div class='row' style='margin-bottom:14px'><a class='btn' href='/caller/leads'>Open Lead Management</a>"
    if actor.role in {"SUPER_ADMIN", "ADMIN"}:
        import_path = "/super-admin/leads/offline-import" if actor.role == "SUPER_ADMIN" else "/admin/leads/offline-import"
        template_path = import_path + "/template"
        body += f"<a class='btn secondary' href='{import_path}'>Upload Leads (Excel)</a><a class='btn secondary' href='{template_path}'>Download Excel Template</a>"
    body += "</div><h3>Lead Source Summary</h3><table><tr><th>Lead Source</th><th>Lead Count</th></tr>" + source_summary + "</table><p class='muted'>Source totals include leads assigned within your permitted team scope.</p></div>"
    csrf = csrf_token(request)
    body += "<div class='card'><h2>Lead Intelligence</h2><p class='muted'>Score leads from 0–100 using source, freshness and captured qualification data.</p>"
    body += f"<form method='post' action='/crm/advanced/score-leads'><input type='hidden' name='csrf_token' value='{csrf}'><button class='btn' type='submit'>Recalculate Lead Scores</button></form></div>"
    body += "<div class='grid'>"
    links = [("Tasks & Follow-up", "/crm/advanced/tasks"), ("Sales Targets", "/crm/advanced/targets"), ("Marketing Campaigns", "/crm/advanced/campaigns"), ("Channel Partners", "/crm/advanced/partners"), ("Payment Milestones", "/crm/advanced/payments"), ("Customer Service", "/crm/advanced/tickets"), ("Possession Checklist", "/crm/advanced/possession")]
    for label, href in links:
        body += f"<div class='card'><h2>{escape(label)}</h2><a class='btn' href='{href}'>Open</a></div>"
    body += "</div>"
    return page("Advanced CRM Hub", body)


@router.post("/crm/advanced/score-leads", dependencies=[Depends(require_csrf)])
def recalculate_scores(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    score_all(actor, db)
    return RedirectResponse("/crm/advanced", status_code=303)


@router.get("/crm/advanced/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    ids = team_ids(actor, db)
    rows = db.scalars(select(CRMTask).where(CRMTask.assigned_user_id.in_(ids)).order_by(CRMTask.due_at.asc()).limit(100)).all()
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username)).all()
    csrf = csrf_token(request)
    body = "<div class='card'><h2>Create task</h2><form method='post' action='/crm/advanced/tasks'><input type='hidden' name='csrf_token' value='" + csrf + "'><div class='two'><div><label>Title</label><input name='title' required></div><div><label>Due</label><input type='datetime-local' name='due_at' required></div><div><label>Assign to</label><select name='assigned_user_id'>" + "".join(f"<option value='{u.id}'>{escape(u.username)} ({escape(str(u.role))})</option>" for u in users) + "</select></div><div><label>Priority</label><select name='priority'><option>LOW</option><option selected>MEDIUM</option><option>HIGH</option><option>URGENT</option></select></div></div><label>Description</label><textarea name='description'></textarea><div style='margin-top:10px'><button class='btn' type='submit'>Create Task</button></div></form></div>"
    body += "<div class='card'><h2>Task queue</h2><table><tr><th>Title</th><th>Assigned</th><th>Due</th><th>Priority</th><th>Status</th><th>Action</th></tr>"
    for row in rows:
        u = db.get(User, row.assigned_user_id)
        action = f"<form method='post' action='/crm/advanced/tasks/{row.id}/done'><input type='hidden' name='csrf_token' value='{csrf}'><button class='btn secondary' type='submit'>Done</button></form>" if row.status != "DONE" else "✓"
        body += f"<tr><td>{escape(row.title)}</td><td>{escape(u.username) if u else row.assigned_user_id}</td><td>{row.due_at}</td><td><span class='pill'>{escape(row.priority)}</span></td><td>{escape(row.status)}</td><td>{action}</td></tr>"
    body += "</table></div>"
    return page("Tasks & Follow-up", body)


@router.post("/crm/advanced/tasks", dependencies=[Depends(require_csrf)])
def create_task(request: Request, title: str = Form(...), due_at: str = Form(...), assigned_user_id: int = Form(...), priority: str = Form("MEDIUM"), description: str = Form(""), db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or not can_manage_team(actor, assigned_user_id, db):
        return RedirectResponse("/crm/advanced/tasks", status_code=303)
    task = CRMTask(title=title.strip(), description=description.strip() or None, assigned_user_id=assigned_user_id, due_at=datetime.fromisoformat(due_at), priority=priority.upper(), created_by_id=actor.id)
    db.add(task); db.commit()
    return RedirectResponse("/crm/advanced/tasks", status_code=303)


@router.post("/crm/advanced/tasks/{task_id}/done", dependencies=[Depends(require_csrf)])
def done_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    task = db.get(CRMTask, task_id)
    if not actor or not task or task.assigned_user_id not in team_ids(actor, db):
        return RedirectResponse("/crm/advanced/tasks", status_code=303)
    task.status = "DONE"; task.completed_at = now(); db.commit()
    return RedirectResponse("/crm/advanced/tasks", status_code=303)


@router.get("/crm/advanced/targets", response_class=HTMLResponse)
def targets_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor: return RedirectResponse("/", status_code=303)
    ids = team_ids(actor, db); rows = db.scalars(select(SalesTarget).where(SalesTarget.user_id.in_(ids)).order_by(SalesTarget.period.desc())).all()
    csrf = csrf_token(request); users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username)).all()
    body = "<div class='card'><h2>Set monthly targets</h2><form method='post' action='/crm/advanced/targets'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>User</label><select name='user_id'>"+"".join(f"<option value='{u.id}'>{escape(u.username)} ({escape(str(u.role))})</option>" for u in users)+"</select></div><div><label>Period (YYYY-MM)</label><input name='period' placeholder='2026-09' required></div><div><label>Lead target</label><input type='number' name='lead_target' min='0' value='0'></div><div><label>Visit target</label><input type='number' name='visit_target' min='0' value='0'></div><div><label>Booking target</label><input type='number' name='booking_target' min='0' value='0'></div><div><label>Sales target</label><input type='number' step='0.01' name='sales_target' min='0' value='0'></div></div><button class='btn' style='margin-top:10px' type='submit'>Save Target</button></form></div>"
    body += "<div class='card'><h2>Targets</h2><table><tr><th>User</th><th>Period</th><th>Leads</th><th>Visits</th><th>Bookings</th><th>Sales</th></tr>"+"".join(f"<tr><td>{escape(db.get(User,r.user_id).username)}</td><td>{escape(r.period)}</td><td>{r.lead_target}</td><td>{r.visit_target}</td><td>{r.booking_target}</td><td>₹ {float(r.sales_target):,.2f}</td></tr>" for r in rows if db.get(User,r.user_id))+"</table></div>"
    return page("Sales Targets", body)


@router.post("/crm/advanced/targets", dependencies=[Depends(require_csrf)])
def create_target(request: Request, user_id: int = Form(...), period: str = Form(...), lead_target: int = Form(0), visit_target: int = Form(0), booking_target: int = Form(0), sales_target: Decimal = Form(0), db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"} or not can_manage_team(actor, user_id, db):
        return RedirectResponse("/crm/advanced/targets", status_code=303)
    existing = db.scalar(select(SalesTarget).where(SalesTarget.user_id == user_id, SalesTarget.period == period))
    if existing:
        existing.lead_target, existing.visit_target, existing.booking_target, existing.sales_target = lead_target, visit_target, booking_target, sales_target
    else:
        db.add(SalesTarget(user_id=user_id, period=period, lead_target=lead_target, visit_target=visit_target, booking_target=booking_target, sales_target=sales_target, created_by_id=actor.id))
    db.commit(); return RedirectResponse("/crm/advanced/targets", status_code=303)


@router.get("/crm/advanced/campaigns", response_class=HTMLResponse)
def campaigns_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN"}: return RedirectResponse("/dashboard", status_code=303)
    rows = db.scalars(select(MarketingCampaign).order_by(MarketingCampaign.id.desc()).limit(100)).all(); csrf = csrf_token(request)
    body = "<div class='card'><h2>Campaign planning & attribution</h2><p class='muted'>Track source, budget and campaign windows now; portal/ad APIs can feed actual lead counts later.</p><form method='post' action='/crm/advanced/campaigns'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Name</label><input name='name' required></div><div><label>Channel</label><select name='channel'><option>PORTAL</option><option>GOOGLE</option><option>META</option><option>WHATSAPP</option><option>SMS</option><option>EMAIL</option><option>OFFLINE</option><option>REFERRAL</option></select></div><div><label>Source tag</label><input name='source'></div><div><label>Budget</label><input type='number' step='0.01' name='budget' value='0'></div><div><label>Start</label><input type='datetime-local' name='start_date'></div><div><label>End</label><input type='datetime-local' name='end_date'></div></div><label>Notes</label><textarea name='notes'></textarea><button class='btn' style='margin-top:10px' type='submit'>Create Campaign</button></form></div>"
    body += "<div class='card'><h2>Campaigns</h2><table><tr><th>Name</th><th>Channel</th><th>Source</th><th>Budget</th><th>Status</th></tr>"+"".join(f"<tr><td>{escape(r.name)}</td><td>{escape(r.channel)}</td><td>{escape(r.source or '—')}</td><td>₹ {float(r.budget):,.2f}</td><td>{escape(r.status)}</td></tr>" for r in rows)+"</table></div>"
    return page("Marketing Campaigns", body)


@router.post("/crm/advanced/campaigns", dependencies=[Depends(require_csrf)])
def create_campaign(request: Request, name: str = Form(...), channel: str = Form(...), source: str = Form(""), budget: Decimal = Form(0), start_date: str = Form(""), end_date: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        return RedirectResponse("/crm/advanced/campaigns", status_code=303)
    parse = lambda value: datetime.fromisoformat(value) if value else None
    db.add(MarketingCampaign(name=name.strip(), channel=channel.upper(), source=source.strip() or None, budget=budget, start_date=parse(start_date), end_date=parse(end_date), notes=notes.strip() or None, created_by_id=actor.id)); db.commit()
    return RedirectResponse("/crm/advanced/campaigns", status_code=303)


@router.get("/crm/advanced/partners", response_class=HTMLResponse)
def partners_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER"}: return RedirectResponse("/dashboard", status_code=303)
    rows = db.scalars(select(ChannelPartner).order_by(ChannelPartner.name)).all(); csrf = csrf_token(request)
    body = "<div class='card'><h2>Channel partner network</h2><form method='post' action='/crm/advanced/partners'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Name</label><input name='name' required></div><div><label>Company</label><input name='company'></div><div><label>Mobile</label><input name='mobile'></div><div><label>Email</label><input name='email' type='email'></div><div><label>Commission %</label><input name='commission_percent' type='number' step='0.0001' min='0' max='100' value='0'></div></div><label>Notes</label><textarea name='notes'></textarea><button class='btn' style='margin-top:10px' type='submit'>Add Partner</button></form></div>"
    body += "<div class='card'><h2>Partners</h2><table><tr><th>Name</th><th>Company</th><th>Mobile</th><th>Commission</th><th>Status</th></tr>"+"".join(f"<tr><td>{escape(r.name)}</td><td>{escape(r.company or '—')}</td><td>{escape(r.mobile or '—')}</td><td>{float(r.commission_percent):.4f}%</td><td>{escape(r.status)}</td></tr>" for r in rows)+"</table></div>"
    return page("Channel Partners", body)


@router.post("/crm/advanced/partners", dependencies=[Depends(require_csrf)])
def create_partner(request: Request, name: str = Form(...), company: str = Form(""), mobile: str = Form(""), email: str = Form(""), commission_percent: Decimal = Form(0), notes: str = Form(""), db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER"}: return RedirectResponse("/crm/advanced/partners", status_code=303)
    db.add(ChannelPartner(name=name.strip(), company=company.strip() or None, mobile=mobile.strip() or None, email=email.strip() or None, commission_percent=commission_percent, notes=notes.strip() or None)); db.commit(); return RedirectResponse("/crm/advanced/partners", status_code=303)


@router.get("/crm/advanced/payments", response_class=HTMLResponse)
def payments_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor: return RedirectResponse("/", status_code=303)
    ids = team_ids(actor, db); bookings = db.scalars(select(Booking).where(or_(Booking.employee_id.in_(ids), Booking.manager_id.in_(ids))).order_by(Booking.id.desc()).limit(100)).all(); booking_ids = [b.id for b in bookings]
    rows = db.scalars(select(PaymentMilestone).where(PaymentMilestone.booking_id.in_(booking_ids)).order_by(PaymentMilestone.due_date.asc())).all() if booking_ids else []
    csrf = csrf_token(request)
    body = "<div class='card'><h2>Payment milestones</h2><p class='muted'>Track booking-linked dues, receipts and overdue collections. Gateway integration can be connected later.</p><form method='post' action='/crm/advanced/payments'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Booking ID</label><select name='booking_id'>"+"".join(f"<option value='{b.id}'>Booking #{b.id}</option>" for b in bookings)+"</select></div><div><label>Milestone</label><input name='milestone_name' required placeholder='Agreement / Slab 1 / Possession'></div><div><label>Due date</label><input type='date' name='due_date' required></div><div><label>Due amount</label><input type='number' step='0.01' name='due_amount' min='0' required></div></div><button class='btn' style='margin-top:10px' type='submit'>Add Milestone</button></form></div>"
    body += "<div class='card'><h2>Collection schedule</h2><table><tr><th>Booking</th><th>Milestone</th><th>Due</th><th>Due Amount</th><th>Received</th><th>Status</th></tr>"+"".join(f"<tr><td>#{r.booking_id}</td><td>{escape(r.milestone_name)}</td><td>{r.due_date.date()}</td><td>₹ {float(r.due_amount):,.2f}</td><td>₹ {float(r.received_amount):,.2f}</td><td>{escape(r.status)}</td></tr>" for r in rows)+"</table></div>"
    return page("Payment Milestones", body)


@router.post("/crm/advanced/payments", dependencies=[Depends(require_csrf)])
def create_payment_milestone(request: Request, booking_id: int = Form(...), milestone_name: str = Form(...), due_date: str = Form(...), due_amount: Decimal = Form(...), db: Session = Depends(get_db)):
    actor = current_user(request, db); booking = db.get(Booking, booking_id)
    if not actor or not booking or booking.employee_id not in team_ids(actor, db) and booking.manager_id not in team_ids(actor, db): return RedirectResponse("/crm/advanced/payments", status_code=303)
    db.add(PaymentMilestone(booking_id=booking_id, milestone_name=milestone_name.strip(), due_date=datetime.fromisoformat(due_date), due_amount=due_amount)); db.commit(); return RedirectResponse("/crm/advanced/payments", status_code=303)


@router.get("/crm/advanced/tickets", response_class=HTMLResponse)
def tickets_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor: return RedirectResponse("/", status_code=303)
    scoped_customer_ids = customer_ids(actor, db)
    rows = db.scalars(select(ServiceTicket).where(ServiceTicket.customer_id.in_(scoped_customer_ids)).order_by(ServiceTicket.id.desc()).limit(100)).all() if scoped_customer_ids else []
    customers = db.scalars(select(Customer).where(Customer.id.in_(scoped_customer_ids)).order_by(Customer.name).limit(100)).all() if scoped_customer_ids else []
    csrf = csrf_token(request)
    body = "<div class='card'><h2>Customer service / complaints</h2><form method='post' action='/crm/advanced/tickets'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Customer</label><select name='customer_id'>"+"".join(f"<option value='{c.id}'>{escape(c.name)} #{c.id}</option>" for c in customers)+"</select></div><div><label>Category</label><select name='category'><option>DOCUMENT</option><option>PAYMENT</option><option>POSSESSION</option><option>PROPERTY</option><option>OTHER</option></select></div><div><label>Subject</label><input name='subject' required></div><div><label>Priority</label><select name='priority'><option>LOW</option><option selected>MEDIUM</option><option>HIGH</option><option>URGENT</option></select></div></div><label>Description</label><textarea name='description'></textarea><button class='btn' style='margin-top:10px' type='submit'>Create Ticket</button></form></div>"
    body += "<div class='card'><h2>Ticket queue</h2><table><tr><th>ID</th><th>Customer</th><th>Category</th><th>Subject</th><th>Priority</th><th>Status</th></tr>"+"".join(f"<tr><td>#{r.id}</td><td>{escape(db.get(Customer,r.customer_id).name) if db.get(Customer,r.customer_id) else r.customer_id}</td><td>{escape(r.category)}</td><td>{escape(r.subject)}</td><td>{escape(r.priority)}</td><td>{escape(r.status)}</td></tr>" for r in rows)+"</table></div>"
    return page("Customer Service", body)


@router.post("/crm/advanced/tickets", dependencies=[Depends(require_csrf)])
def create_ticket(request: Request, customer_id: int = Form(...), category: str = Form(...), subject: str = Form(...), priority: str = Form("MEDIUM"), description: str = Form(""), db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor or customer_id not in customer_ids(actor, db): return RedirectResponse("/crm/advanced/tickets", status_code=303)
    db.add(ServiceTicket(customer_id=customer_id, assigned_user_id=actor.id, category=category.upper(), subject=subject.strip(), priority=priority.upper(), description=description.strip() or None)); db.commit(); return RedirectResponse("/crm/advanced/tickets", status_code=303)


@router.get("/crm/advanced/possession", response_class=HTMLResponse)
def possession_page(request: Request, db: Session = Depends(get_db)):
    actor = current_user(request, db)
    if not actor: return RedirectResponse("/", status_code=303)
    ids = team_ids(actor, db); bookings = db.scalars(select(Booking).where(or_(Booking.employee_id.in_(ids), Booking.manager_id.in_(ids))).order_by(Booking.id.desc()).limit(100)).all(); booking_ids=[b.id for b in bookings]
    rows = db.scalars(select(PossessionChecklist).where(PossessionChecklist.booking_id.in_(booking_ids)).order_by(PossessionChecklist.booking_id, PossessionChecklist.id)).all() if booking_ids else []
    csrf=csrf_token(request)
    body="<div class='card'><h2>Possession checklist</h2><form method='post' action='/crm/advanced/possession'><input type='hidden' name='csrf_token' value='"+csrf+"'><div class='two'><div><label>Booking</label><select name='booking_id'>"+"".join(f"<option value='{b.id}'>Booking #{b.id}</option>" for b in bookings)+"</select></div><div><label>Checklist item</label><input name='item' required placeholder='Agreement / NOC / Inspection / Keys'></div></div><button class='btn' style='margin-top:10px' type='submit'>Add Checklist Item</button></form></div>"
    body+="<div class='card'><h2>Handover checklist</h2><table><tr><th>Booking</th><th>Item</th><th>Done</th></tr>"+"".join(f"<tr><td>#{r.booking_id}</td><td>{escape(r.item)}</td><td>{'YES' if r.completed else 'PENDING'}</td></tr>" for r in rows)+"</table></div>"
    return page("Possession Checklist", body)


@router.post("/crm/advanced/possession", dependencies=[Depends(require_csrf)])
def add_possession_item(request: Request, booking_id: int = Form(...), item: str = Form(...), db: Session = Depends(get_db)):
    actor=current_user(request,db); booking=db.get(Booking,booking_id); ids=team_ids(actor,db) if actor else set()
    if not actor or not booking or (booking.employee_id not in ids and booking.manager_id not in ids): return RedirectResponse("/crm/advanced/possession", status_code=303)
    db.add(PossessionChecklist(booking_id=booking_id,item=item.strip())); db.commit(); return RedirectResponse("/crm/advanced/possession", status_code=303)
