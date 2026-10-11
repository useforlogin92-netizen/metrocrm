from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, CustomerRequirement, Lead, LeadAssignmentHistory, User

router = APIRouter(prefix="/caller", tags=["caller-leads"])


def current_user(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _visible_user_ids(user: User, db: Session) -> set[int] | None:
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        return None
    ids = {user.id}
    if user.role in {"MANAGER", "TL"}:
        frontier = {user.id}
        while frontier:
            children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
            frontier = {int(uid) for uid in children if int(uid) not in ids}
            ids.update(frontier)
    return ids


@router.get("/leads", response_class=HTMLResponse)
def caller_leads(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or user.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}:
        return RedirectResponse("/", status_code=303)
    visible_user_ids = _visible_user_ids(user, db)
    lead_query = select(Lead).order_by(Lead.created_at.desc()).limit(200)
    if visible_user_ids is not None:
        lead_query = select(Lead).where((Lead.assigned_user_id.in_(visible_user_ids)) | (Lead.assigned_user_id.is_(None) & (user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}))).order_by(Lead.created_at.desc()).limit(200)
    leads = db.scalars(lead_query).all()
    assignable_users = []
    if user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}:
        assignable_query = select(User).where(User.is_active.is_(True), User.role.in_(["SALES_EXECUTIVE", "TELECALLER"])).order_by(User.username.asc())
        if user.role in {"MANAGER", "TL"}:
            team_ids = _visible_user_ids(user, db) or {user.id}
            assignable_query = assignable_query.where(User.id.in_(team_ids))
        assignable_users = db.scalars(assignable_query).all()
    rows = []
    for lead in leads:
        customer = db.get(Customer, lead.customer_id) if lead.customer_id else None
        requirement = db.scalar(select(CustomerRequirement).where(CustomerRequirement.customer_id == lead.customer_id, CustomerRequirement.is_active.is_(True)).order_by(CustomerRequirement.updated_at.desc(), CustomerRequirement.id.desc())) if lead.customer_id else None
        project_name = ((requirement.project_preference or '').strip() if requirement else '') or 'Property not selected'
        mobile = (customer.mobile or '').strip() if customer else ''
        digits = ''.join(ch for ch in mobile if ch.isdigit())
        email = (customer.email or '').strip() if customer else ''
        phone_action = f'<a class="btn" href="tel:{escape(mobile, quote=True)}">Call</a>' if len(digits) >= 7 else '<span>Number unavailable</span>'
        whatsapp_action = f'<a class="btn whatsapp" target="_blank" rel="noopener noreferrer" href="https://wa.me/{digits}">WhatsApp</a>' if len(digits) >= 10 else '<span>WhatsApp unavailable</span>'
        email_action = f'<a class="btn email" href="mailto:{escape(email, quote=True)}">Email</a>' if email else '<span>Email unavailable</span>'
        assignment_action = ""
        if user.role in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}:
            options = "".join(f'<option value="{target.id}" {"selected" if lead.assigned_user_id == target.id else ""}>{escape(target.username)}</option>' for target in assignable_users)
            assignment_action = f'<form method="post" action="/caller/leads/{lead.id}/assign"><input type="hidden" name="csrf_token" value="{csrf_token(request)}"><select name="target_user_id" required>{options}</select><input name="reason" required minlength="3" maxlength="500" placeholder="Assignment reason"><button class="btn" type="submit">Assign</button></form>' if options else '<span>No active callers available</span>'
        rows.append(f'<tr><td>{lead.id}</td><td>{escape(customer.name if customer else "Unlinked")}</td><td>{escape(mobile) if mobile else "Number unavailable"}</td><td>{phone_action}<br>{whatsapp_action}<br>{email_action}</td><td>{escape(lead.source or "")}</td><td>{escape(lead.preferred_location or "")}</td><td>{escape(project_name)}</td><td>{escape(lead.bhk or "")}</td><td>{escape(lead.status or "")}</td><td>{assignment_action}</td><td><a class="btn" href="/caller/lead/{lead.id}/call">Start Call</a></td></tr>')
    body = """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | My Leads</title><style>body{font-family:Inter,Arial,sans-serif;background:#f5f7fb;color:#10213f;margin:0;padding:24px}.wrap{max-width:1200px;margin:auto}.card{background:#fff;border:1px solid #e5eaf2;border-radius:16px;padding:20px;box-shadow:0 5px 20px #0000000a}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:11px;border-bottom:1px solid #eef2f7;text-align:left}th{background:#f8fafc}.btn{display:inline-block;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;padding:8px 12px;font-weight:750}.page-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.page-nav a,.page-nav button{display:inline-block;border:1px solid #cbd5e1;background:#fff;color:#10213f;text-decoration:none;border-radius:8px;padding:8px 12px;font:inherit;font-size:12px;font-weight:750;cursor:pointer}.page-nav a:hover,.page-nav button:hover:not(:disabled){background:#eff6ff;border-color:#93c5fd}.page-nav button:disabled{opacity:.45;cursor:not-allowed;background:#f8fafc;color:#94a3b8}@media(max-width:700px){table{display:block;overflow:auto;white-space:nowrap}.page-nav a,.page-nav button{flex:1;text-align:center}}</style></head><body><div class='wrap'><div class='card'><nav class='page-nav' aria-label='Page navigation'><a href='/dashboard'>Dashboard</a><button id='metrocrm-history-back' type='button' disabled aria-label='Go back to the previous page'>← Back</button><button id='metrocrm-history-forward' type='button' disabled aria-label='Go forward to the next page'>Forward →</button></nav><h1>My Leads — Call Assistant</h1><p>Select a lead and click Start Call. The opening script and matching property script will be prepared automatically.</p><table><tr><th>ID</th><th>Customer</th><th>Mobile Number</th><th>Contact Actions</th><th>Source</th><th>Location</th><th>Property / Project Name</th><th>BHK</th><th>Status</th><th>Assign Caller</th><th>Call Assistant</th></tr>""" + ("".join(rows) or "<tr><td colspan='11'>No leads found.</td></tr>") + "</table></div></div><script>(function(){const back=document.getElementById('metrocrm-history-back');const forward=document.getElementById('metrocrm-history-forward');if(!back||!forward)return;function sync(){if('navigation' in window&&window.navigation){back.disabled=!window.navigation.canGoBack;forward.disabled=!window.navigation.canGoForward;return;}back.disabled=window.history.length<=1;forward.disabled=false;}back.addEventListener('click',function(){if(back.disabled)return;if('navigation' in window&&window.navigation)window.navigation.back();else window.history.back();});forward.addEventListener('click',function(){if(forward.disabled)return;if('navigation' in window&&window.navigation)window.navigation.forward();else window.history.forward();});window.addEventListener('pageshow',sync);window.addEventListener('popstate',sync);if('navigation' in window&&window.navigation){window.navigation.addEventListener('currententrychange',sync);window.navigation.addEventListener('navigate',sync);}sync();})();</script></body></html>"
    return HTMLResponse(body)


@router.post("/leads/{lead_id}/assign")
def assign_caller_lead(
    lead_id: int,
    request: Request,
    target_user_id: int = Form(...),
    reason: str = Form(..., min_length=3, max_length=500),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    actor = current_user(request, db)
    if not actor or actor.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}:
        return HTMLResponse("Forbidden", status_code=403)
    lead = db.get(Lead, lead_id)
    target = db.get(User, target_user_id)
    if not lead or not target or not target.is_active or target.role not in {"SALES_EXECUTIVE", "TELECALLER"}:
        return HTMLResponse("Invalid lead or active caller", status_code=400)
    if actor.role in {"MANAGER", "TL"}:
        visible_ids = _visible_user_ids(actor, db) or {actor.id}
        if lead.assigned_user_id is not None and lead.assigned_user_id not in visible_ids:
            return HTMLResponse("Forbidden: lead outside your team", status_code=403)
        if target.id not in visible_ids and target.reporting_manager_id not in visible_ids:
            return HTMLResponse("Forbidden: caller outside your team", status_code=403)
    previous_id = lead.assigned_user_id
    lead.assigned_user_id = target.id
    db.add(LeadAssignmentHistory(lead_id=lead.id, from_user_id=previous_id, to_user_id=target.id, assigned_by_id=actor.id, reason=reason.strip()))
    db.add(AuditEvent(actor_user_id=actor.id, action="LEAD_ASSIGNED_FROM_CALLER_WORKSPACE", entity_type="Lead", entity_id=str(lead.id), details=f"from_user_id={previous_id};to_user_id={target.id};reason={reason.strip()}"))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse("/caller/leads", status_code=303)
