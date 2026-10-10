from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Lead, User

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
        lead_query = select(Lead).where(Lead.assigned_user_id.in_(visible_user_ids)).order_by(Lead.created_at.desc()).limit(200)
    leads = db.scalars(lead_query).all()
    rows = []
    for lead in leads:
        customer = db.get(Customer, lead.customer_id) if lead.customer_id else None
        rows.append(f"<tr><td>{lead.id}</td><td>{escape(customer.name if customer else 'Unlinked')}</td><td>{escape(lead.source or '')}</td><td>{escape(lead.preferred_location or '')}</td><td>{escape(lead.bhk or '')}</td><td>{escape(lead.status or '')}</td><td><a class='btn' href='/caller/lead/{lead.id}/call'>Start Call</a></td></tr>")
    body = """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM | My Leads</title><style>body{font-family:Inter,Arial,sans-serif;background:#f5f7fb;color:#10213f;margin:0;padding:24px}.wrap{max-width:1200px;margin:auto}.card{background:#fff;border:1px solid #e5eaf2;border-radius:16px;padding:20px;box-shadow:0 5px 20px #0000000a}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:11px;border-bottom:1px solid #eef2f7;text-align:left}th{background:#f8fafc}.btn{display:inline-block;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;padding:8px 12px;font-weight:750}.page-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.page-nav a,.page-nav button{display:inline-block;border:1px solid #cbd5e1;background:#fff;color:#10213f;text-decoration:none;border-radius:8px;padding:8px 12px;font:inherit;font-size:12px;font-weight:750;cursor:pointer}.page-nav a:hover,.page-nav button:hover{background:#eff6ff;border-color:#93c5fd}@media(max-width:700px){table{display:block;overflow:auto;white-space:nowrap}.page-nav a,.page-nav button{flex:1;text-align:center}}</style></head><body><div class='wrap'><div class='card'><nav class='page-nav' aria-label='Page navigation'><a href='/dashboard'>Dashboard</a><button type='button' onclick='window.history.back()' aria-label='Go back to the previous page'>← Back</button><button type='button' onclick='window.history.forward()' aria-label='Go forward to the next page'>Forward →</button></nav><h1>My Leads — Call Assistant</h1><p>Select a lead and click Start Call. The opening script and matching property script will be prepared automatically.</p><table><tr><th>ID</th><th>Customer</th><th>Source</th><th>Locations</th><th>BHK</th><th>Status</th><th>Call</th></tr>""" + ("".join(rows) or "<tr><td colspan='7'>No leads found.</td></tr>") + "</table></div></div></body></html>"
    return HTMLResponse(body)
