from __future__ import annotations

from datetime import datetime
from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.ui_navigation import add_history_navigation
from app.database import get_db
from app.models import AuditEvent, Customer, FollowUp, Lead, LeadAssignmentHistory, SiteVisit, User

router = APIRouter(prefix="/admin/lead-monitoring", tags=["lead-visit-monitoring"])
ADMIN_ROLES = {"SUPER_ADMIN", "ADMIN"}
TEAM_ROLES = {"MANAGER", "TL"}
ASSIGN_ROLES = ADMIN_ROLES | TEAM_ROLES
MONITOR_ROLES = ASSIGN_ROLES | {"SALES_EXECUTIVE", "TELECALLER"}


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _dt(value: datetime | None) -> str:
    return value.strftime("%d %b %Y, %I:%M %p") if value else "—"


def _lead_health_score(lead: Lead, followups: list[FollowUp], now: datetime) -> tuple[int, list[str]]:
    """Transparent rule-based signal; managers make the final reassignment decision."""
    score = 100
    reasons: list[str] = []
    related = [f for f in followups if f.lead_id == lead.id and not f.completed]
    overdue = [f for f in related if f.due_at <= now]
    if not lead.assigned_user_id:
        score -= 20
        reasons.append("Unassigned")
    if overdue:
        score -= min(45, 20 + 10 * (len(overdue) - 1))
        reasons.append(f"{len(overdue)} overdue follow-up(s)")
    age_days = max(0, (now - lead.created_at).days) if lead.created_at else 0
    if age_days >= 3 and not related and (lead.status or "").upper() not in {"WON", "LOST", "CLOSED", "CONVERTED"}:
        score -= 25
        reasons.append("No pending follow-up scheduled")
    if age_days >= 2 and (lead.status or "").upper() in {"NEW", "ASSIGNED"}:
        score -= 15
        reasons.append("Lead status has not progressed")
    if not reasons:
        reasons.append("No rule-based risk flags")
    return max(0, min(100, score)), reasons


def _scope_user_ids(actor: User, db: Session) -> set[int]:
    if actor.role in ADMIN_ROLES:
        return set(db.scalars(select(User.id)).all())
    if actor.role not in TEAM_ROLES:
        return {actor.id}
    ids = {actor.id}
    frontier = {actor.id}
    while frontier:
        children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
        frontier = {int(user_id) for user_id in children if int(user_id) not in ids}
        ids.update(frontier)
    return ids


def _lead_in_scope(actor: User, lead: Lead, db: Session) -> bool:
    if actor.role in ADMIN_ROLES:
        return True
    return lead.assigned_user_id in _scope_user_ids(actor, db)


def _can_reassign(actor: User) -> bool:
    return actor.role in ASSIGN_ROLES


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in MONITOR_ROLES:
        return RedirectResponse("/", status_code=303)

    now = datetime.now()
    scope_ids = _scope_user_ids(actor, db)
    leads_query = select(Lead).order_by(Lead.created_at.desc()).limit(500)
    followup_query = select(FollowUp).where(FollowUp.completed.is_(False)).order_by(FollowUp.due_at.asc()).limit(500)
    visit_query = select(SiteVisit).order_by(SiteVisit.scheduled_at.asc()).limit(500)
    if actor.role not in ADMIN_ROLES:
        leads_query = select(Lead).where(Lead.assigned_user_id.in_(scope_ids)).order_by(Lead.created_at.desc()).limit(500)
        followup_query = select(FollowUp).where(FollowUp.completed.is_(False), FollowUp.assigned_user_id.in_(scope_ids)).order_by(FollowUp.due_at.asc()).limit(500)
        visit_query = select(SiteVisit).join(Lead, SiteVisit.lead_id == Lead.id).where(
            or_(Lead.assigned_user_id.in_(scope_ids), SiteVisit.sales_employee_id.in_(scope_ids))
        ).order_by(SiteVisit.scheduled_at.asc()).limit(500)
    leads = db.scalars(leads_query).all()
    followups = db.scalars(followup_query).all()
    visits = db.scalars(visit_query).all()
    users = db.scalars(select(User).where(User.is_active.is_(True), User.id.in_(scope_ids), User.role.in_({"MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"})).order_by(User.username)).all()
    user_map = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(scope_ids))).all()}
    customer_map = {c.id: c for c in db.scalars(select(Customer)).all()}
    overdue_calls = [f for f in followups if f.due_at <= now]
    upcoming_visits = [v for v in visits if v.scheduled_at >= now and (v.status or "").upper() not in {"CANCELLED", "COMPLETED", "DONE"}]
    missed_visits = [v for v in visits if v.scheduled_at < now and (v.status or "").upper() not in {"CANCELLED", "COMPLETED", "DONE", "NO_SHOW", "CUSTOMER_NO_SHOW"}]

    lead_rows = []
    for lead in leads:
        customer = customer_map.get(lead.customer_id)
        owner = user_map.get(lead.assigned_user_id, "Unassigned")
        health, health_reasons = _lead_health_score(lead, followups, now)
        health_label = "Needs review" if health < 60 else ("Watch" if health < 80 else "Healthy")
        options = "".join(f'<option value="{u.id}">{escape(u.username)}</option>' for u in users)
        action_cell = (
            f"<td><form method='post' action='/admin/lead-monitoring/reassign-lead'>"
            f"<input type='hidden' name='csrf_token' value='{escape(csrf_token(request))}'>"
            f"<input type='hidden' name='lead_id' value='{lead.id}'>"
            f"<select name='assigned_user_id' required><option value=''>Select caller</option>{options}</select>"
            "<input name='reason' placeholder='Reason (optional)' maxlength='300'>"
            "<button type='submit'>Assign</button></form></td>"
            if _can_reassign(actor) else "<td>—</td>"
        )
        lead_rows.append(
            "<tr>"
            f"<td><a href='/admin/lead-monitoring/report/{lead.id}'>#{lead.id} · Caller Report</a></td><td>{escape(customer.name if customer else 'Unlinked')}</td>"
            f"<td>{escape(lead.source or 'Unknown')}</td><td>{escape(owner)}</td>"
            f"<td>{escape(lead.status or 'NEW')}</td><td title='{escape('; '.join(health_reasons))}'>{health}/100 · {escape(health_label)}</td><td>{_dt(lead.created_at)}</td>"
            f"{action_cell}</tr>"
        )

    follow_rows = []
    for f in followups:
        lead = db.get(Lead, f.lead_id) if f.lead_id else None
        customer = customer_map.get(f.customer_id) if f.customer_id else (customer_map.get(lead.customer_id) if lead else None)
        state = "OVERDUE" if f.due_at <= now else "UPCOMING"
        follow_rows.append(f"<tr><td>{escape(state)}</td><td>{escape(customer.name if customer else '—')}</td><td>{escape(lead.source if lead and lead.source else '—')}</td><td>{escape(user_map.get(f.assigned_user_id, 'Unassigned'))}</td><td>{_dt(f.due_at)}</td><td>{escape(f.purpose or 'Call follow-up')}</td><td>{escape(f.notes or '')}</td></tr>")

    visit_rows = []
    for visit in visits:
        customer = customer_map.get(visit.customer_id)
        options = "".join(f'<option value="{u.id}">{escape(u.username)}</option>' for u in users)
        status = (visit.status or "SCHEDULED").upper()
        attention = "OVERDUE" if visit.scheduled_at < now and status not in {"CANCELLED", "COMPLETED", "DONE", "NO_SHOW", "CUSTOMER_NO_SHOW"} else status
        action_cell = (
            f"<td><form method='post' action='/admin/lead-monitoring/reassign-visit'>"
            f"<input type='hidden' name='csrf_token' value='{escape(csrf_token(request))}'>"
            f"<input type='hidden' name='visit_id' value='{visit.id}'>"
            f"<select name='assigned_user_id' required><option value=''>Backup caller</option>{options}</select>"
            f"<input name='reason' placeholder='Reason (optional)' maxlength='300'><button type='submit'>Reassign visit</button></form></td>"
            if _can_reassign(actor) else "<td>—</td>"
        )
        visit_rows.append(
            f"<tr><td>#{visit.id}</td><td>{escape(customer.name if customer else '—')}</td>"
            f"<td>{escape(user_map.get(visit.sales_employee_id, 'Unassigned'))}</td><td>{_dt(visit.scheduled_at)}</td>"
            f"<td><strong>{escape(attention)}</strong></td><td>{escape(visit.outcome or '')}</td>"
            f"{action_cell}</tr>"
        )

    body = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MetroCRM | Lead & Visit Monitoring</title><style>
body{{font:14px Inter,Arial,sans-serif;background:#f4f7fb;color:#152238;margin:0;padding:24px}}main{{max-width:1500px;margin:auto}}.top,.card{{background:#fff;border:1px solid #e0e7f0;border-radius:14px;padding:20px;margin-bottom:16px}}.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.stat{{background:#f8fafc;border:1px solid #e5eaf2;border-radius:10px;padding:15px}}.num{{font-size:26px;font-weight:800;margin-top:6px}}.tablewrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:900px}}th,td{{padding:10px;border-bottom:1px solid #e8edf4;text-align:left;vertical-align:top}}th{{background:#f8fafc;position:sticky;top:0}}input,select,button{{font:inherit;padding:8px;border:1px solid #cbd5e1;border-radius:7px;margin:2px;max-width:180px}}button{{background:#1d4ed8;color:white;border:0;font-weight:700;cursor:pointer}}.alert{{border-left:4px solid #dc2626;background:#fff7f7;padding:12px;margin:8px 0}}.muted{{color:#64748b}}@media(max-width:750px){{body{{padding:10px}}.stats{{grid-template-columns:1fr 1fr}}.top,.card{{padding:12px}}}}</style></head><body><main>
<div class='top'><h1>Lead & Visit Monitoring</h1><p class='muted'>{escape(actor.role.title().replace('_', ' '))}: {escape(actor.username)} · Showing leads, follow-ups and visits within your permitted scope.</p>
<div class='stats'><div class='stat'>Total leads<div class='num'>{len(leads)}</div></div><div class='stat'>Unassigned leads<div class='num'>{sum(1 for l in leads if not l.assigned_user_id)}</div></div><div class='stat'>Overdue follow-ups<div class='num'>{len(overdue_calls)}</div></div><div class='stat'>Upcoming visits<div class='num'>{len(upcoming_visits)}</div></div></div></div>
<div class='card'><h2>Alerts needing attention</h2>
{''.join(f"<div class='alert'>Overdue follow-up · {escape((customer_map.get(f.customer_id).name if f.customer_id and customer_map.get(f.customer_id) else 'Lead follow-up'))} · Caller {escape(user_map.get(f.assigned_user_id, 'Unassigned'))} · Due {_dt(f.due_at)}</div>" for f in overdue_calls[:50]) or "<p>No overdue follow-ups currently recorded.</p>"}
{''.join(f"<div class='alert'>Visit requires status update · Visit #{v.id} · {escape(customer_map.get(v.customer_id).name if v.customer_id and customer_map.get(v.customer_id) else 'Customer not linked')} · Scheduled {_dt(v.scheduled_at)} · Current status {escape(v.status or 'SCHEDULED')}</div>" for v in missed_visits[:50]) or "<p>No past-due visits requiring status update.</p>"}
</div>
<div class='card'><h2>{'All leads & reassignment' if _can_reassign(actor) else 'My assigned leads'}</h2><p class='muted'>Lead source is shown on every row. {('Team scope applies.' if actor.role in TEAM_ROLES else 'Only your assigned leads are shown.')} Reassignment records the acting manager/admin and reason in the audit log.</p><div class='tablewrap'><table><thead><tr><th>Lead / Caller Report</th><th>Customer</th><th>Source</th><th>Assigned caller</th><th>Status</th><th>Health</th><th>Received</th><th>{'Assign / reassign' if _can_reassign(actor) else 'Action'}</th></tr></thead><tbody>{''.join(lead_rows) or '<tr><td colspan="8">No leads found.</td></tr>'}</tbody></table></div></div>
<div class='card'><h2>Call follow-ups</h2><div class='tablewrap'><table><thead><tr><th>Alert</th><th>Customer</th><th>Source</th><th>Caller</th><th>Due</th><th>Purpose</th><th>Notes</th></tr></thead><tbody>{''.join(follow_rows) or '<tr><td colspan="7">No open follow-ups found.</td></tr>'}</tbody></table></div></div>
<div class='card'><h2>{'Site visit monitoring & backup assignment' if _can_reassign(actor) else 'My site visits'}</h2><div class='tablewrap'><table><thead><tr><th>Visit</th><th>Customer</th><th>Visit owner</th><th>Scheduled time</th><th>Status / alert</th><th>Outcome</th><th>{'Reassign' if _can_reassign(actor) else 'Action'}</th></tr></thead><tbody>{''.join(visit_rows) or '<tr><td colspan="7">No site visits found.</td></tr>'}</tbody></table></div></div>
</main></body></html>"""
    return HTMLResponse(add_history_navigation(body))


@router.post("/reassign-lead")
def reassign_lead(request: Request, lead_id: int = Form(...), assigned_user_id: int = Form(...), reason: str = Form(""), csrf_token_value: str = Form("", alias="csrf_token"), db: Session = Depends(get_db)):
    require_csrf(request, csrf_token_value)
    actor = _actor(request, db)
    if not actor or not _can_reassign(actor):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    target = db.get(User, assigned_user_id)
    scope_ids = _scope_user_ids(actor, db)
    if not lead or not _lead_in_scope(actor, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    if not target or not target.is_active or target.role not in {"MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"} or target.id not in scope_ids:
        return HTMLResponse("Select an active caller within your permitted team.", status_code=400)
    previous = lead.assigned_user_id
    lead.assigned_user_id = target.id
    db.add(LeadAssignmentHistory(lead_id=lead.id, from_user_id=previous, to_user_id=target.id, assigned_by_id=actor.id, reason=reason[:300] or None))
    db.add(AuditEvent(actor_user_id=actor.id, action="LEAD_REASSIGNED", entity_type="Lead", entity_id=str(lead.id), details=f"from={previous};to={target.id};reason={reason[:300]}"))
    db.commit()
    return RedirectResponse("/admin/lead-monitoring", status_code=303)


@router.post("/reassign-visit")
def reassign_visit(request: Request, visit_id: int = Form(...), assigned_user_id: int = Form(...), reason: str = Form(""), csrf_token_value: str = Form("", alias="csrf_token"), db: Session = Depends(get_db)):
    require_csrf(request, csrf_token_value)
    actor = _actor(request, db)
    if not actor or not _can_reassign(actor):
        return RedirectResponse("/", status_code=303)
    visit = db.get(SiteVisit, visit_id)
    target = db.get(User, assigned_user_id)
    lead = db.get(Lead, visit.lead_id) if visit and visit.lead_id else None
    scope_ids = _scope_user_ids(actor, db)
    if not visit or not lead or not _lead_in_scope(actor, lead, db):
        return HTMLResponse("Visit not found or outside your permitted scope.", status_code=404)
    if not target or not target.is_active or target.role not in {"MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"} or target.id not in scope_ids:
        return HTMLResponse("Select an active caller within your permitted team.", status_code=400)
    previous = visit.sales_employee_id
    visit.sales_employee_id = target.id
    db.add(AuditEvent(actor_user_id=actor.id, action="SITE_VISIT_REASSIGNED", entity_type="SiteVisit", entity_id=str(visit.id), details=f"from={previous};to={target.id};reason={reason[:300]}"))
    db.commit()
    return RedirectResponse("/admin/lead-monitoring", status_code=303)

@router.get("/report/{lead_id}", response_class=HTMLResponse)
def caller_lead_report(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """Show the lead's status, follow-up notes and full assignment trail."""
    actor = _actor(request, db)
    if not actor or actor.role not in MONITOR_ROLES:
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead or not _lead_in_scope(actor, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    customer = db.get(Customer, lead.customer_id) if lead.customer_id else None
    users = {u.id: u.username for u in db.scalars(select(User)).all()}
    history = db.scalars(
        select(LeadAssignmentHistory).where(LeadAssignmentHistory.lead_id == lead.id)
        .order_by(LeadAssignmentHistory.created_at.desc(), LeadAssignmentHistory.id.desc())
    ).all()
    followups = db.scalars(
        select(FollowUp).where(FollowUp.lead_id == lead.id)
        .order_by(FollowUp.due_at.desc(), FollowUp.id.desc())
    ).all()
    history_rows = "".join(
        f"<tr><td>{_dt(h.created_at)}</td><td>{escape(users.get(h.from_user_id, 'Unassigned'))}</td>"
        f"<td>{escape(users.get(h.to_user_id, 'Unassigned'))}</td><td>{escape(users.get(h.assigned_by_id, 'Unknown'))}</td>"
        f"<td>{escape(h.reason or '—')}</td></tr>" for h in history
    ) or "<tr><td colspan='5'>No assignment history recorded.</td></tr>"
    follow_rows = "".join(
        f"<tr><td>{_dt(f.due_at)}</td><td>{escape('Completed' if f.completed else 'Pending')}</td>"
        f"<td>{escape(users.get(f.assigned_user_id, 'Unassigned'))}</td><td>{escape(f.purpose or 'Call follow-up')}</td>"
        f"<td>{escape(f.notes or '—')}</td></tr>" for f in followups
    ) or "<tr><td colspan='5'>No follow-ups recorded.</td></tr>"
    transfer_scope_ids = _scope_user_ids(actor, db)
    target_users = db.scalars(select(User).where(
        User.is_active.is_(True), User.id.in_(transfer_scope_ids),
        User.role.in_({"SALES_EXECUTIVE", "TELECALLER"})
    ).order_by(User.username)).all()
    options = "".join(f"<option value='{u.id}'>{escape(u.username)}</option>" for u in target_users if u.id != lead.assigned_user_id)
    transfer = ""
    if _can_reassign(actor):
        transfer = f"""
        <section><h2>Transfer lead to another caller</h2>
        <p>Previous call notes and follow-up history remain attached. Pending follow-ups will be reassigned to the new caller.</p>
        <form method='post' action='/admin/lead-monitoring/transfer-lead'>
        <input type='hidden' name='csrf_token' value='{escape(csrf_token(request))}'>
        <input type='hidden' name='lead_id' value='{lead.id}'>
        <select name='assigned_user_id' required><option value=''>Select caller</option>{options}</select>
        <textarea name='reason' required minlength='3' maxlength='500' placeholder='Transfer reason / handover notes (required)'></textarea>
        <button type='submit'>Transfer lead with history</button></form></section>"""
    body = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Caller Report — Lead #{lead.id}</title><style>
    body{{font:14px Arial,sans-serif;background:#f4f7fb;color:#17243a;padding:20px}}main{{max-width:1250px;margin:auto}}section{{background:white;border:1px solid #e1e8f0;border-radius:12px;padding:18px;margin-bottom:16px}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e8edf4;vertical-align:top}}textarea,select,button{{font:inherit;padding:9px;margin:4px;border:1px solid #cbd5e1;border-radius:7px}}textarea{{display:block;width:min(700px,95%);min-height:75px}}button{{background:#1d4ed8;color:white;border:0;font-weight:700}}.wrap{{overflow:auto}}</style></head><body><main>
    <p><a href='/admin/lead-monitoring'>← Lead & Visit Monitoring</a> · <a href='/caller/leads'>Caller Leads</a></p>
    <section><h1>Caller Report — Lead #{lead.id}</h1><p><b>Customer:</b> {escape(customer.name if customer else 'Unlinked')} · <b>Source:</b> {escape(lead.source or 'Unknown')} · <b>Status:</b> {escape(lead.status or 'NEW')} · <b>Caller:</b> {escape(users.get(lead.assigned_user_id, 'Unassigned'))}</p>
    <p><b>Location:</b> {escape(lead.preferred_location or '—')} · <b>BHK:</b> {escape(lead.bhk or '—')} · <b>Requirement:</b> {escape(lead.requirement or '—')}</p></section>
    <section><h2>Lead Health</h2><p>Rule-based triage only; this score does not automatically reassign a lead. The manager reviews the reasons and decides the next action.</p><p><b>Health score:</b> { _lead_health_score(lead, followups, datetime.now())[0] }/100 · <b>Risk signals:</b> {escape('; '.join(_lead_health_score(lead, followups, datetime.now())[1]))}</p></section><section><h2>Assignment & transfer history</h2><div class='wrap'><table><thead><tr><th>Date</th><th>From caller</th><th>To caller</th><th>Assigned by</th><th>Reason / handover comment</th></tr></thead><tbody>{history_rows}</tbody></table></div></section>
    <section><h2>Follow-up report</h2><div class='wrap'><table><thead><tr><th>Due</th><th>Status</th><th>Caller</th><th>Purpose</th><th>Notes / comments</th></tr></thead><tbody>{follow_rows}</tbody></table></div></section>
    {transfer}</main></body></html>"""
    return HTMLResponse(add_history_navigation(body))


@router.post("/transfer-lead", dependencies=[Depends(require_csrf)])
def transfer_lead(
    request: Request,
    lead_id: int = Form(...),
    assigned_user_id: int = Form(...),
    reason: str = Form(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    if not actor or not _can_reassign(actor):
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    target = db.get(User, assigned_user_id)
    scope_ids = _scope_user_ids(actor, db)
    if not lead or not _lead_in_scope(actor, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    if not target or not target.is_active or target.role not in {"SALES_EXECUTIVE", "TELECALLER"} or target.id not in scope_ids:
        return HTMLResponse("Select an active caller within your permitted team.", status_code=400)
    if target.id == lead.assigned_user_id:
        return HTMLResponse("Lead is already assigned to this caller.", status_code=409)
    handover = reason.strip()
    if len(handover) < 3:
        return HTMLResponse("A transfer reason and handover comment are required.", status_code=422)
    previous = lead.assigned_user_id
    pending_followups = db.scalars(
        select(FollowUp).where(FollowUp.lead_id == lead.id, FollowUp.completed.is_(False))
    ).all()
    lead.assigned_user_id = target.id
    if lead.original_owner_id is None:
        lead.original_owner_id = previous or target.id
    for followup in pending_followups:
        followup.assigned_user_id = target.id
        # Keep existing notes intact; the handover comment is stored in assignment history.
    db.add(LeadAssignmentHistory(
        lead_id=lead.id, from_user_id=previous, to_user_id=target.id,
        assigned_by_id=actor.id, reason=handover,
    ))
    db.add(AuditEvent(
        actor_user_id=actor.id, action="LEAD_TRANSFERRED_WITH_HANDOVER",
        entity_type="Lead", entity_id=str(lead.id),
        details=f"from={previous};to={target.id};pending_followups_reassigned={len(pending_followups)};handover={handover}",
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        return HTMLResponse("Transfer failed; no changes were saved. Please retry or contact an administrator.", status_code=500)
    return RedirectResponse(f"/admin/lead-monitoring/report/{lead.id}", status_code=303)

