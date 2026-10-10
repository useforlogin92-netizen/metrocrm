"""Manager-approved, workload-based lead assignment suggestions."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, LeadAssignmentHistory, User
from app.services.lead_assignment_recommendations import CLOSED_STATUSES, recommend_lead_assignees

router = APIRouter(prefix="/admin/lead-assignment-suggestions", tags=["lead-assignment"])
MANAGEMENT_ROLES = {"SUPER_ADMIN", "ADMIN", "TL"}
CALLER_ROLES = {"SALES_EXECUTIVE", "TELECALLER"}


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _scope(actor: User, db: Session) -> tuple[list[User], set[int] | None]:
    callers = db.scalars(
        select(User).where(User.is_active.is_(True), User.role.in_(CALLER_ROLES)).order_by(User.username)
    ).all()
    if actor.role in {"SUPER_ADMIN", "ADMIN"}:
        return callers, None
    # Team Leads can only manage their direct reports or users in their own team.
    scoped = [
        user for user in callers
        if (actor.team and user.team == actor.team) or user.reporting_manager_id == actor.id
    ]
    return scoped, {user.id for user in scoped}


def _visible_leads(actor: User, db: Session, scoped_ids: set[int] | None) -> list[Lead]:
    query = select(Lead).order_by(Lead.created_at.desc()).limit(200)
    if scoped_ids is not None:
        if not scoped_ids:
            return []
        query = select(Lead).where(Lead.assigned_user_id.in_(scoped_ids)).order_by(Lead.created_at.desc()).limit(200)
    return db.scalars(query).all()


@router.get("", response_class=HTMLResponse)
def suggestions(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in MANAGEMENT_ROLES:
        return RedirectResponse("/", status_code=303)

    callers, scoped_ids = _scope(actor, db)
    leads = _visible_leads(actor, db, scoped_ids)
    closed = [status.upper() for status in CLOSED_STATUSES]
    workload_rows = db.execute(
        select(Lead.assigned_user_id, func.count(Lead.id))
        .where(Lead.assigned_user_id.is_not(None), func.upper(Lead.status).not_in(closed))
        .group_by(Lead.assigned_user_id)
    ).all()
    workloads = {int(user_id): int(count) for user_id, count in workload_rows if user_id is not None}
    customers = {c.id: c for c in db.scalars(select(Customer)).all()}
    rows = []
    for lead in leads:
        customer = customers.get(lead.customer_id)
        recommendations = recommend_lead_assignees(lead, callers, workloads, limit=3)
        options = "".join(
            f'<option value="{item["user_id"]}">{escape(item["username"])} — {item["open_lead_count"]} open leads</option>'
            for item in recommendations
        )
        summary = ", ".join(
            f'{escape(item["username"])} ({item["open_lead_count"]} open)'
            for item in recommendations
        ) or "No eligible caller"
        can_assign = bool(recommendations) and (scoped_ids is None or lead.assigned_user_id in (scoped_ids or set()))
        form = (
            f"<form method='post' action='/admin/lead-assignment-suggestions/approve'>"
            f"<input type='hidden' name='csrf_token' value='{escape(csrf_token(request))}'>"
            f"<input type='hidden' name='lead_id' value='{lead.id}'>"
            f"<select name='assigned_user_id' required>{options}</select>"
            "<input name='reason' maxlength='300' placeholder='Approval reason' required>"
            "<button type='submit'>Approve & Assign</button></form>"
            if can_assign else "<span class='muted'>No eligible caller / outside team scope</span>"
        )
        rows.append(
            f"<tr><td>#{lead.id}</td><td>{escape(customer.name if customer else 'Unlinked')}</td>"
            f"<td>{escape(lead.source or 'Unknown')}</td><td>{escape(lead.preferred_location or '')}</td>"
            f"<td>{escape(lead.status or 'NEW')}</td><td>{escape(summary)}</td><td>{form}</td></tr>"
        )
    body = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MetroCRM | Assignment Suggestions</title><style>
body{{font:14px Arial,sans-serif;background:#f4f7fb;color:#17243a;margin:0;padding:24px}}main{{max-width:1400px;margin:auto}}section{{background:#fff;border:1px solid #e1e8f0;border-radius:14px;padding:20px}}table{{border-collapse:collapse;width:100%;min-width:1000px}}.wrap{{overflow:auto}}th,td{{padding:10px;border-bottom:1px solid #e8edf4;text-align:left;vertical-align:top}}th{{background:#f8fafc}}input,select,button{{font:inherit;padding:8px;border:1px solid #cbd5e1;border-radius:7px;margin:2px;max-width:230px}}button{{background:#1d4ed8;color:white;border:0;font-weight:700}}.muted{{color:#64748b}}p{{color:#475569}}
</style></head><body><main><section><h1>Lead Assignment Suggestions</h1>
<p>Suggestions balance current open-lead workload. This is advisory only: an Admin, Super Admin or appropriately scoped TL must explicitly approve an assignment. Area/language specialisation is not scored because reliable caller coverage fields are not currently defined in the User schema.</p>
<div class='wrap'><table><thead><tr><th>Lead</th><th>Customer</th><th>Source</th><th>Location</th><th>Status</th><th>Recommended callers</th><th>Approval</th></tr></thead><tbody>{''.join(rows) or "<tr><td colspan='7'>No leads in your permitted scope.</td></tr>"}</tbody></table></div></section></main></body></html>"""
    return HTMLResponse(body)


@router.post("/approve", dependencies=[Depends(require_csrf)])
def approve_assignment(
    request: Request,
    lead_id: int = Form(...),
    assigned_user_id: int = Form(...),
    reason: str = Form(..., min_length=1, max_length=300),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    if not actor or actor.role not in MANAGEMENT_ROLES:
        return RedirectResponse("/", status_code=303)

    callers, scoped_ids = _scope(actor, db)
    eligible_ids = {user.id for user in callers}
    if assigned_user_id not in eligible_ids:
        return HTMLResponse("Selected caller is not eligible in your scope.", status_code=403)

    lead = db.get(Lead, lead_id)
    if lead is None:
        return HTMLResponse("Lead not found.", status_code=404)
    if scoped_ids is not None and lead.assigned_user_id not in scoped_ids:
        return HTMLResponse("Lead is outside your team scope.", status_code=403)
    if lead.assigned_user_id == assigned_user_id:
        return HTMLResponse("Lead is already assigned to this caller.", status_code=409)

    if not reason.strip():
        return HTMLResponse("Approval reason is required.", status_code=422)

    previous_owner = lead.assigned_user_id
    lead.assigned_user_id = assigned_user_id
    if lead.original_owner_id is None:
        lead.original_owner_id = assigned_user_id
    db.add(LeadAssignmentHistory(
        lead_id=lead.id,
        from_user_id=previous_owner,
        to_user_id=assigned_user_id,
        assigned_by_id=actor.id,
        reason=reason.strip(),
    ))
    db.add(AuditEvent(
        actor_user_id=actor.id,
        action="LEAD_ASSIGNMENT_APPROVED",
        entity_type="Lead",
        entity_id=str(lead.id),
        details=f"from_user_id={previous_owner};to_user_id={assigned_user_id};reason={reason.strip()}",
    ))
    db.commit()
    return RedirectResponse("/admin/lead-assignment-suggestions", status_code=303)
