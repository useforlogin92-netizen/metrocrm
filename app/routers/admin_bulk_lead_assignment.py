"""Admin-only all-leads queue with audited bulk caller assignment."""
from __future__ import annotations

from html import escape
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, FollowUp, Lead, LeadAssignmentHistory, User

router = APIRouter(prefix="/admin/all-leads", tags=["bulk-lead-assignment"])
ADMIN_ROLES = {"SUPER_ADMIN", "ADMIN"}
CALLER_ROLES = {"SALES_EXECUTIVE", "TELECALLER"}
PAGE_SIZE = 100


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _admin_only(request: Request, db: Session) -> User | None:
    actor = _actor(request, db)
    return actor if actor and actor.role in ADMIN_ROLES else None


def _query_filters(query, q: str, status: str, assigned: str):
    if q.strip():
        term = f"%{q.strip()}%"
        search_terms = [
            Customer.name.ilike(term),
            Customer.mobile.ilike(term),
            Lead.source.ilike(term),
            Lead.preferred_location.ilike(term),
        ]
        if q.strip().isdigit():
            search_terms.append(Lead.id == int(q.strip()))
        query = query.where(or_(*search_terms))
    if status.strip():
        query = query.where(Lead.status == status.strip())
    if assigned == "unassigned":
        query = query.where(Lead.assigned_user_id.is_(None))
    elif assigned.isdigit():
        query = query.where(Lead.assigned_user_id == int(assigned))
    return query


@router.get("", response_class=HTMLResponse)
def all_leads(
    request: Request,
    q: str = "",
    status: str = "",
    assigned: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    actor = _admin_only(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)

    page = max(1, page)
    count_query = _query_filters(
        select(func.count(Lead.id)).select_from(Lead).outerjoin(Customer, Customer.id == Lead.customer_id),
        q, status, assigned,
    )
    total = int(db.scalar(count_query) or 0)
    lead_query = _query_filters(
        select(Lead).outerjoin(Customer, Customer.id == Lead.customer_id),
        q, status, assigned,
    ).order_by(Lead.created_at.desc(), Lead.id.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    leads = db.scalars(lead_query).all()
    customers = {
        customer.id: customer
        for customer in db.scalars(
            select(Customer).where(Customer.id.in_({lead.customer_id for lead in leads if lead.customer_id}))
        ).all()
    } if leads else {}
    users = {user.id: user for user in db.scalars(select(User)).all()}
    lead_ids_on_page = [lead.id for lead in leads]
    followups_by_lead: dict[int, list[FollowUp]] = {}
    if lead_ids_on_page:
        followups = db.scalars(
            select(FollowUp).where(FollowUp.lead_id.in_(lead_ids_on_page)).order_by(FollowUp.due_at.desc(), FollowUp.id.desc())
        ).all()
        for followup in followups:
            if followup.lead_id is not None:
                followups_by_lead.setdefault(followup.lead_id, []).append(followup)
    callers = db.scalars(
        select(User).where(User.is_active.is_(True), User.role.in_(CALLER_ROLES)).order_by(User.username.asc())
    ).all()
    statuses = ["NEW", "OPEN", "CONTACTED", "FOLLOW_UP", "QUALIFIED", "SITE_VISIT", "BOOKED", "CLOSED", "LOST"]

    rows = []
    for lead in leads:
        customer = customers.get(lead.customer_id)
        owner = users.get(lead.assigned_user_id) if lead.assigned_user_id else None
        mobile = customer.mobile if customer and customer.mobile else ""
        budget = " – ".join(
            [f"₹{lead.budget_min:,.0f}" if lead.budget_min is not None else "",
             f"₹{lead.budget_max:,.0f}" if lead.budget_max is not None else ""]
        ).strip(" –") or "—"
        lead_followups = followups_by_lead.get(lead.id, [])
        if lead_followups:
            followup_items = "".join(
                "<li>"
                f"<strong>{escape(followup.due_at.strftime('%d %b %Y, %I:%M %p') if followup.due_at else 'No due date')}</strong> — "
                f"<span>{'Completed' if followup.completed else 'Pending'}</span>"
                f"<small>{escape(followup.purpose or 'Follow-up')}{(' · ' + escape(followup.notes)) if followup.notes else ''}</small>"
                "</li>"
                for followup in lead_followups
            )
            followup_cell = f"<details class='followups'><summary>View follow-ups ({len(lead_followups)})</summary><ul>{followup_items}</ul></details>"
        else:
            followup_cell = "<span class='muted'>No follow-ups</span>"
        rows.append(
            "<tr>"
            f"<td><input class='lead-select' type='checkbox' name='lead_ids' value='{lead.id}' aria-label='Select lead {lead.id}'></td>"
            f"<td>#{lead.id}<br><strong>{escape(customer.name if customer else 'Unlinked')}</strong>"
            f"<small>{escape(mobile)}</small></td>"
            f"<td>{escape(lead.source or '—')}</td>"
            f"<td>{escape(lead.preferred_location or '—')}</td>"
            f"<td>{escape(lead.bhk or '—')}<small>{escape(budget)}</small></td>"
            f"<td>{escape(lead.status or 'NEW')}</td>"
            f"<td>{escape(owner.username if owner else 'Unassigned')}</td>"
            f"<td>{followup_cell}</td>"
            f"<td><a class='btn secondary' href='/caller/lead/{lead.id}/call'>Open Call</a></td>"
            "</tr>"
        )

    caller_options = "".join(
        f"<option value='{caller.id}'>{escape(caller.username)} ({escape(caller.role.replace('_', ' ').title())})</option>"
        for caller in callers
    )
    status_options = "<option value=''>All statuses</option>" + "".join(
        f"<option value='{value}' {'selected' if status == value else ''}>{value.replace('_', ' ').title()}</option>"
        for value in statuses
    )
    owner_options = "<option value=''>All assignments</option><option value='unassigned' " + (
        "selected" if assigned == "unassigned" else ""
    ) + ">Unassigned</option>" + "".join(
        f"<option value='{user.id}' {'selected' if assigned == str(user.id) else ''}>{escape(user.username)}</option>"
        for user in callers
    )
    base_query = f"q={quote_plus(q)}&status={quote_plus(status)}&assigned={quote_plus(assigned)}"
    previous_link = (
        f"<a class='btn secondary' href='/admin/all-leads?page={page - 1}&{base_query}'>← Previous</a>"
        if page > 1 else ""
    )
    next_link = (
        f"<a class='btn secondary' href='/admin/all-leads?page={page + 1}&{base_query}'>Next →</a>"
        if page * PAGE_SIZE < total else ""
    )
    token = escape(csrf_token(request), quote=True)
    batch_count = request.query_params.get("assigned_batch", "")
    batch_notice = (
        f"<p class='success' role='status'>Assignment complete: {int(batch_count)} lead(s) assigned or reassigned.</p>"
        if batch_count.isdigit() else ""
    )
    body = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | All Leads</title>
<style>
*{{box-sizing:border-box}}body{{font:14px Inter,Arial,sans-serif;background:#f3f6fb;color:#14233b;margin:0;padding:24px}}
main{{max-width:1500px;margin:auto}}.card{{background:#fff;border:1px solid #dfe7f1;border-radius:15px;padding:22px;box-shadow:0 5px 20px #0f172a08}}
nav,.filters,.bulk,.pager{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}}
h1{{margin:8px 0}}p,.muted,small{{color:#64748b}}small{{display:block;margin-top:4px;font-size:11px}}
input,select{{font:inherit;padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;max-width:100%}}
input[type=checkbox]{{width:17px;height:17px;accent-color:#2563eb}}.btn{{display:inline-block;padding:10px 13px;border:0;border-radius:8px;background:#2563eb;color:white;text-decoration:none;font-weight:750;cursor:pointer}}
.secondary{{background:#fff;color:#172b4d;border:1px solid #cbd5e1}}.filters input{{min-width:220px}}.bulk{{padding:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px}}
.table-wrap{{overflow:auto}}table{{width:100%;min-width:1000px;border-collapse:collapse}}th,td{{padding:12px;border-bottom:1px solid #edf1f6;text-align:left;vertical-align:middle}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;background:#f8fafc}}td small{{max-width:200px;overflow-wrap:anywhere}}.followups{{min-width:170px;max-width:280px}}.followups summary{{cursor:pointer;color:#1d4ed8;font-weight:700}}.followups ul{{padding-left:18px;margin:8px 0}}.followups li{{margin:0 0 10px;overflow-wrap:anywhere}}
.pager{{justify-content:space-between;margin-top:16px}}.count{{font-weight:750;color:#334155}}.warning{{color:#9a3412;font-size:12px}}.success{{padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;color:#166534;font-weight:700}}
@media(max-width:700px){{body{{padding:10px}}.card{{padding:13px}}.filters>*{{width:100%}}.bulk>*{{width:100%}}}}
</style></head><body><main><section class='card'>
<nav><a class='btn secondary' href='/dashboard'>← Dashboard</a><a class='btn secondary' href='/admin/all-leads/history'>Assignment History</a><a class='btn secondary' href='/caller/leads'>Caller Lead Workspace</a></nav>
<h1>All Leads</h1>{batch_notice}<p>Review all CRM leads and assign multiple selected leads to an active Sales Executive or Telecaller.</p>
<form class='filters' method='get' action='/admin/all-leads'>
<input name='q' value='{escape(q, quote=True)}' placeholder='Search name, mobile, lead ID, source, location'>
<select name='status'>{status_options}</select><select name='assigned'>{owner_options}</select>
<button class='btn' type='submit'>Apply Filters</button><a class='btn secondary' href='/admin/all-leads'>Clear</a>
</form>
<div class='count'>Showing {((page - 1) * PAGE_SIZE) + (1 if leads else 0)}–{min(page * PAGE_SIZE, total)} of {total} leads · Page {page}</div>
<form method='post' action='/admin/all-leads/bulk-assign' id='bulk-assignment-form'>
<input type='hidden' name='csrf_token' value='{token}'>
<div class='bulk'>
<strong id='selected-count'>0 selected</strong>
<select name='assigned_user_id' required aria-label='Assign selected leads to caller'><option value=''>Choose caller to assign</option>{caller_options}</select>
<input name='reason' required minlength='3' maxlength='300' placeholder='Assignment reason (required)'>
<button class='btn' type='submit'>Assign Selected Leads</button>
<span class='warning'>Only checked leads on this page will be assigned.</span>
</div>
<div class='table-wrap'><table><thead><tr><th><input id='select-page' type='checkbox' aria-label='Select all leads on this page'></th><th>Lead / Customer</th><th>Source</th><th>Location</th><th>BHK / Budget</th><th>Lead Status</th><th>Current Caller</th><th>Follow-up</th><th>Action</th></tr></thead>
<tbody>{''.join(rows) or "<tr><td colspan='9'>No leads match these filters.</td></tr>"}</tbody></table></div>
</form><div class='pager'><span class='muted'>Bulk assignment is recorded in assignment history.</span><div>{previous_link} {next_link}</div></div>
</section></main><script>
(function(){{const master=document.getElementById('select-page');const boxes=[...document.querySelectorAll('.lead-select')];const count=document.getElementById('selected-count');function sync(){{const n=boxes.filter(b=>b.checked).length;count.textContent=n+' selected';if(master){{master.checked=boxes.length>0&&n===boxes.length;master.indeterminate=n>0&&n<boxes.length;}}}}if(master)master.addEventListener('change',()=>{{boxes.forEach(b=>b.checked=master.checked);sync();}});boxes.forEach(b=>b.addEventListener('change',sync));document.getElementById('bulk-assignment-form').addEventListener('submit',e=>{{if(!boxes.some(b=>b.checked)){{e.preventDefault();alert('Select at least one lead before assigning.');return;}}if(!confirm('Assign '+boxes.filter(b=>b.checked).length+' selected lead(s) to the chosen caller?'))e.preventDefault();}});sync();}})();
</script></body></html>"""
    return HTMLResponse(body)


@router.post("/bulk-assign", dependencies=[Depends(require_csrf)])
def bulk_assign(
    request: Request,
    lead_ids: list[int] = Form(default=[]),
    assigned_user_id: int = Form(...),
    reason: str = Form(..., min_length=3, max_length=300),
    db: Session = Depends(get_db),
):
    actor = _admin_only(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    ids = list(dict.fromkeys(lead_ids))
    if not ids:
        return HTMLResponse("Select at least one lead.", status_code=422)
    if len(ids) > PAGE_SIZE:
        return HTMLResponse("Select no more than 100 leads per batch.", status_code=422)
    reason = reason.strip()
    if len(reason) < 3:
        return HTMLResponse("Assignment reason must contain at least 3 characters.", status_code=422)

    target = db.get(User, assigned_user_id)
    if not target or not target.is_active or target.role not in CALLER_ROLES:
        return HTMLResponse("Selected user is not an active Sales Executive or Telecaller.", status_code=422)
    leads = db.scalars(select(Lead).where(Lead.id.in_(ids))).all()
    if len(leads) != len(ids):
        return HTMLResponse("One or more selected leads were not found. No leads were changed.", status_code=404)

    changed_count = 0
    try:
        for lead in leads:
            previous_owner = lead.assigned_user_id
            if previous_owner == target.id:
                continue
            lead.assigned_user_id = target.id
            changed_count += 1
            if lead.original_owner_id is None:
                lead.original_owner_id = target.id
            db.add(LeadAssignmentHistory(
                lead_id=lead.id,
                from_user_id=previous_owner,
                to_user_id=target.id,
                assigned_by_id=actor.id,
                reason=reason,
            ))
            db.add(AuditEvent(
                actor_user_id=actor.id,
                action="LEADS_BULK_ASSIGNED",
                entity_type="Lead",
                entity_id=str(lead.id),
                details=f"from_user_id={previous_owner};to_user_id={target.id};reason={reason}",
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(
        f"/admin/all-leads?assigned={target.id}&assigned_batch={changed_count}",
        status_code=303,
    )


@router.get("/history", response_class=HTMLResponse)
def assignment_history(request: Request, db: Session = Depends(get_db)):
    actor = _admin_only(request, db)
    if not actor:
        return RedirectResponse("/", status_code=303)
    history = db.scalars(
        select(LeadAssignmentHistory).order_by(LeadAssignmentHistory.created_at.desc(), LeadAssignmentHistory.id.desc()).limit(300)
    ).all()
    user_ids = {
        uid for item in history for uid in (item.from_user_id, item.to_user_id, item.assigned_by_id) if uid is not None
    }
    users = {user.id: user.username for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    lead_ids = {item.lead_id for item in history}
    leads = {lead.id: lead for lead in db.scalars(select(Lead).where(Lead.id.in_(lead_ids))).all()} if lead_ids else {}
    rows = []
    for item in history:
        lead = leads.get(item.lead_id)
        customer = db.get(Customer, lead.customer_id) if lead and lead.customer_id else None
        rows.append(
            f"<tr><td>#{item.lead_id}<small>{escape(customer.name if customer else 'Unlinked')}</small></td>"
            f"<td>{escape(users.get(item.from_user_id, 'Unassigned') if item.from_user_id else 'Unassigned')}</td>"
            f"<td>{escape(users.get(item.to_user_id, 'Unassigned') if item.to_user_id else 'Unassigned')}</td>"
            f"<td>{escape(users.get(item.assigned_by_id, 'Unknown'))}</td><td>{escape(item.reason or '')}</td>"
            f"<td>{escape(str(item.created_at or ''))}</td></tr>"
        )
    body = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>MetroCRM | Assignment History</title><style>body{font:14px Arial,sans-serif;background:#f3f6fb;color:#14233b;padding:22px}"
        "main{max-width:1300px;margin:auto;background:white;border:1px solid #dfe7f1;border-radius:14px;padding:22px}"
        "nav{display:flex;gap:10px;margin-bottom:16px}a{padding:9px 12px;border:1px solid #cbd5e1;border-radius:8px;text-decoration:none;color:#14233b}"
        ".wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:850px}th,td{padding:11px;border-bottom:1px solid #edf1f6;text-align:left}"
        "th{background:#f8fafc}small{display:block;color:#64748b;margin-top:3px}</style></head><body><main>"
        "<nav><a href='/admin/all-leads'>← All Leads</a><a href='/dashboard'>Dashboard</a></nav>"
        "<h1>Lead Assignment History</h1><p>Latest 300 recorded assignments, including bulk assignment and reassignment events.</p>"
        "<div class='wrap'><table><thead><tr><th>Lead / Customer</th><th>Previous Caller</th><th>New Caller</th><th>Assigned By</th><th>Reason</th><th>Timestamp</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=6>No assignment history found.</td></tr>'}</tbody></table></div></main></body></html>"
    )
    return HTMLResponse(body)
