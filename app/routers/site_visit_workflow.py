from __future__ import annotations

from datetime import datetime
from html import escape
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, FollowUp, Lead, Project, SiteVisit, User
from app.site_visit_workflow_models import DeveloperSalesContact, SiteVisitReview

router = APIRouter(prefix="/site-visits", tags=["site-visit-workflow"])
ALLOWED_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}


def _actor(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _team_user_ids(actor: User, db: Session) -> set[int]:
    if actor.role not in {"MANAGER", "TL"}:
        return {actor.id}
    ids = {actor.id}
    frontier = {actor.id}
    while frontier:
        children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
        frontier = {int(user_id) for user_id in children if int(user_id) not in ids}
        ids.update(frontier)
    return ids


def _visible_lead(actor: User, lead: Lead, db: Session | None = None) -> bool:
    if actor.role in {"SUPER_ADMIN", "ADMIN"}:
        return True
    if lead.assigned_user_id == actor.id:
        return True
    if db is None or actor.role not in {"MANAGER", "TL"}:
        return False
    return lead.assigned_user_id in _team_user_ids(actor, db)


@router.get("", response_class=HTMLResponse)
def visit_workflow(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in ALLOWED_ROLES:
        return RedirectResponse("/", status_code=303)
    leads_query = select(Lead).order_by(Lead.created_at.desc()).limit(300)
    if actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        leads_query = select(Lead).where(Lead.assigned_user_id.in_(_team_user_ids(actor, db))).order_by(Lead.created_at.desc()).limit(300)
    leads = db.scalars(leads_query).all()
    customers = {c.id: c for c in db.scalars(select(Customer)).all()}
    projects = db.scalars(select(Project).order_by(Project.name)).all()
    staff = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_({"SUPER_ADMIN","ADMIN","MANAGER","TL","SALES_EXECUTIVE","TELECALLER"})).order_by(User.username)).all()
    query = select(SiteVisit).order_by(SiteVisit.scheduled_at.desc()).limit(200)
    if actor.role not in {"SUPER_ADMIN", "ADMIN"}:
        query = select(SiteVisit).join(Lead, SiteVisit.lead_id == Lead.id).where(Lead.assigned_user_id.in_(_team_user_ids(actor, db))).order_by(SiteVisit.scheduled_at.desc()).limit(200)
    visits = db.scalars(query).all()
    user_map = {u.id: u.username for u in db.scalars(select(User)).all()}
    project_map = {p.id: p for p in projects}
    review_map = {r.visit_id: r for r in db.scalars(select(SiteVisitReview).where(SiteVisitReview.visit_id.in_([v.id for v in visits]))).all()} if visits else {}
    rows = []
    for v in visits:
        customer = customers.get(v.customer_id) if v.customer_id else (customers.get(db.get(Lead, v.lead_id).customer_id) if v.lead_id and db.get(Lead, v.lead_id) else None)
        review = review_map.get(v.id)
        customer_name = escape(customer.name if customer else "—")
        project_name = escape(project_map[v.project_id].name if v.project_id in project_map else "—")
        caller_name = escape(user_map.get(review.called_by_id, "—") if review else "—")
        coordinator_name = escape(user_map.get(v.conducted_by_id, "—"))
        developer_contact = db.scalar(select(DeveloperSalesContact).where(DeveloperSalesContact.visit_id == v.id))
        sm_name = escape(developer_contact.sm_name if developer_contact and developer_contact.sm_name else (user_map.get(review.sm_id, user_map.get(v.sales_employee_id, "—")) if review else user_map.get(v.sales_employee_id, "—")))
        sm_phone = escape(developer_contact.sm_phone if developer_contact and developer_contact.sm_phone else "—")
        scheduled_text = escape(v.scheduled_at.strftime("%d %b %Y %I:%M %p"))
        visit_status = escape(v.status or "SCHEDULED")
        deal_status = escape(review.deal_status if review else "FEEDBACK PENDING")
        rows.append(
            f"<tr><td>#{v.id}</td><td>{customer_name}</td><td>{project_name}</td>"
            f"<td>{caller_name}</td><td>{coordinator_name}</td><td>{sm_name}<br><small>{sm_phone}</small></td>"
            f"<td>{scheduled_text}</td><td>{visit_status}</td><td>{deal_status}</td>"
            f'<td><a href="/site-visits/{v.id}/feedback">Feedback / Next Step</a></td></tr>'
        )
    csrf = escape(csrf_token(request))
    lead_opts = "".join(f'<option value="{l.id}">#{l.id} · {escape(customers[l.customer_id].name if l.customer_id in customers else "Customer not linked")} · {escape(l.source or "Unknown source")}</option>' for l in leads)
    project_opts = "".join(f'<option value="{p.id}">{escape(p.name)} — {escape(p.locality or p.city or "")}</option>' for p in projects)
    staff_opts = "".join(f'<option value="{u.id}">{escape(u.username)} ({escape(u.role)})</option>' for u in staff)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MetroCRM | Site Visit Workflow</title>
<style>body{{font:14px Arial,sans-serif;background:#f4f7fb;color:#172033;margin:0;padding:22px}}main{{max-width:1500px;margin:auto}}.card{{background:#fff;border:1px solid #e1e7f0;border-radius:14px;padding:20px;margin-bottom:16px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}label{{display:block;font-weight:700;margin:8px 0 5px}}input,select,textarea{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;box-sizing:border-box}}select[multiple]{{min-height:120px}}textarea{{min-height:75px}}button,.btn{{background:#1d4ed8;color:#fff;padding:10px 14px;border:0;border-radius:8px;font-weight:700;text-decoration:none;cursor:pointer}}table{{width:100%;border-collapse:collapse;min-width:1100px}}th,td{{padding:10px;border-bottom:1px solid #e8edf4;text-align:left;vertical-align:top}}th{{background:#f8fafc}}.scroll{{overflow:auto}}.hint{{color:#64748b;font-size:12px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}body{{padding:10px}}}}</style></head><body><main>
<div class="card"><h1>Site Visit & Post-Visit Workflow</h1><p>Record the caller, visit coordinator, developer Sales Manager contact, customer and project details, visit feedback, deal status, and next follow-up. Multiple projects can be scheduled for the same customer at the same date and time.</p><p><a class="btn" href="/dashboard">Dashboard</a> <a class="btn" href="/admin/lead-monitoring">Lead & Visit Monitoring</a></p></div>
<div class="card"><h2>Schedule Site Visit</h2><form method="post" action="/site-visits/create"><input type="hidden" name="csrf_token" value="{csrf}"><div class="grid">
<div><label>Lead / Customer *</label><select name="lead_id" required><option value="">Select lead</option>{lead_opts}</select></div>
<div><label>Visit date & time *</label><input name="scheduled_at" type="datetime-local" required></div>
<div><label>Call Arranged By *</label><select name="called_by_id" required><option value="">Select caller</option>{staff_opts}</select></div>
<div><label>Visit Coordinator *</label><select name="conducted_by_id" required><option value="">Select visit coordinator</option>{staff_opts}</select></div>
<div><label>Developer SM ka naam</label><input name="developer_sm_name" maxlength="160" placeholder="Developer sales manager name"></div>
<div><label>Developer SM ka mobile number</label><input name="developer_sm_phone" type="tel" maxlength="30" pattern="[0-9+() -]{7,30}" placeholder="Developer SM contact number"></div>
<div><label>Initial notes</label><input name="notes" maxlength="1000" placeholder="Customer requirement / meeting notes"></div>
<div style="grid-column:1/-1"><label>Projects to visit * (multiple select supported)</label><select name="project_ids" multiple required>{project_opts}</select><p class="hint">Use Ctrl/⌘ to select multiple projects. A separate visit record will be created for each project, linked to the same customer, date/time, and visit batch.</p></div>
</div><p><button type="submit">Create Visit Plan</button></p></form></div>
<div class="card"><h2>Recent Site Visits</h2><div class="scroll"><table><thead><tr><th>Visit</th><th>Customer</th><th>Project</th><th>Caller</th><th>Visit Conducted By</th><th>SM</th><th>Date / Time</th><th>Status</th><th>Deal</th><th>Action</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="10">No visits found yet.</td></tr>'}</tbody></table></div></div>
</main></body></html>"""
    return HTMLResponse(body)


@router.post("/create", dependencies=[Depends(require_csrf)])
def create_visit_batch(
    request: Request,
    lead_id: int = Form(...),
    scheduled_at: str = Form(...),
    called_by_id: int = Form(...),
    conducted_by_id: int = Form(...),
    developer_sm_name: str = Form(""),
    developer_sm_phone: str = Form(""),
    project_ids: list[int] = Form(...),
    notes: str = Form(""),
    csrf_token_value: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf_token_value)
    actor = _actor(request, db)
    if not actor or actor.role not in ALLOWED_ROLES:
        return RedirectResponse("/", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead or not _visible_lead(actor, lead, db):
        return HTMLResponse("Lead not found or outside your permitted scope.", status_code=404)
    try:
        when = datetime.fromisoformat(scheduled_at)
    except ValueError:
        return HTMLResponse("Invalid visit date/time.", status_code=400)
    if not project_ids or len(set(project_ids)) != len(project_ids):
        return HTMLResponse("Select at least one project without duplicates.", status_code=400)
    for uid in [called_by_id, conducted_by_id]:
        user = db.get(User, uid)
        if not user or not user.is_active:
            return HTMLResponse("Selected staff member is unavailable.", status_code=400)
    projects = [db.get(Project, pid) for pid in project_ids]
    if any(p is None for p in projects):
        return HTMLResponse("One or more selected projects were not found.", status_code=400)
    batch_key = str(uuid4())
    created_ids = []
    try:
        for project in projects:
            visit = SiteVisit(
                customer_id=lead.customer_id, lead_id=lead.id, project_id=project.id,
                sales_employee_id=None, conducted_by_id=conducted_by_id,
                scheduled_at=when, status="SCHEDULED", notes=notes.strip() or None,
            )
            db.add(visit)
            db.flush()
            db.add(SiteVisitReview(visit_id=visit.id, batch_key=batch_key, called_by_id=called_by_id, sm_id=None, deal_status="FOLLOW_UP_REQUIRED", updated_by_id=actor.id))
            db.add(DeveloperSalesContact(visit_id=visit.id, sm_name=developer_sm_name.strip() or None, sm_phone=developer_sm_phone.strip() or None))
            created_ids.append(visit.id)
        db.add(AuditEvent(actor_user_id=actor.id, action="SITE_VISIT_BATCH_CREATED", entity_type="SiteVisitBatch", entity_id=batch_key, details=f'{{"lead_id":{lead.id},"visit_ids":{created_ids},"project_count":{len(created_ids)}}}'))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse("/site-visits", status_code=303)


@router.get("/{visit_id}/feedback", response_class=HTMLResponse)
def visit_feedback_page(visit_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in ALLOWED_ROLES:
        return RedirectResponse("/", status_code=303)
    visit = db.get(SiteVisit, visit_id)
    lead = db.get(Lead, visit.lead_id) if visit and visit.lead_id else None
    if not visit or not lead or not _visible_lead(actor, lead):
        return HTMLResponse("Visit not found or outside your permitted scope.", status_code=404)
    customer = db.get(Customer, visit.customer_id) if visit.customer_id else None
    project = db.get(Project, visit.project_id) if visit.project_id else None
    review = db.scalar(select(SiteVisitReview).where(SiteVisitReview.visit_id == visit.id))
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.username)).all()
    projects = db.scalars(select(Project).order_by(Project.name)).all()
    csrf = escape(csrf_token(request))
    user_opts = "".join(f'<option value="{u.id}">{escape(u.username)}</option>' for u in users)
    project_opts = "".join(f'<option value="{p.id}" {"selected" if review and review.next_project_id == p.id else ""}>{escape(p.name)}</option>' for p in projects)
    developer_contact = db.scalar(select(DeveloperSalesContact).where(DeveloperSalesContact.visit_id == visit.id))
    developer_sm_name = developer_contact.sm_name if developer_contact and developer_contact.sm_name else "—"
    developer_sm_phone = developer_contact.sm_phone if developer_contact and developer_contact.sm_phone else "—"
    def val(x): return escape(str(x or ""))
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Visit Feedback</title><style>body{{font:14px Arial;background:#f4f7fb;margin:0;padding:22px;color:#172033}}main{{max-width:1000px;margin:auto}}.card{{background:#fff;padding:22px;border-radius:14px;border:1px solid #e1e7f0;margin-bottom:16px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}label{{display:block;font-weight:700;margin:8px 0 5px}}input,select,textarea{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;box-sizing:border-box}}textarea{{min-height:90px}}button,.btn{{background:#1d4ed8;color:white;padding:10px 14px;border:0;border-radius:8px;text-decoration:none;font-weight:700}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><main><div class="card"><h1>Post-Visit Feedback — Visit #{visit.id}</h1><p><b>Customer:</b> {val(customer.name if customer else '—')} · <b>Project:</b> {val(project.name if project else '—')} · <b>Scheduled:</b> {val(visit.scheduled_at)}</p><p><b>Lead source:</b> {val(lead.source)} · <b>Customer contact:</b> {val(customer.mobile if customer else '')} · <b>Developer SM:</b> {val(developer_sm_name)} · <b>SM Contact:</b> {val(developer_sm_phone)}</p><a class="btn" href="/site-visits">Back to Visits</a></div>
<div class="card"><form method="post" action="/site-visits/{visit.id}/feedback"><input type="hidden" name="csrf_token" value="{csrf}"><div class="grid">
<div><label>Visit status</label><select name="status">{''.join(f'<option value="{s}" {"selected" if (visit.status or "SCHEDULED")==s else ""}>{s.replace("_"," ").title()}</option>' for s in ["SCHEDULED","COMPLETED","RESCHEDULED","CANCELLED","NO_SHOW","CUSTOMER_NO_SHOW"])}</select></div>
<div><label>Customer interest</label><select name="interest_level">{''.join(f'<option value="{s}" {"selected" if review and review.interest_level==s else ""}>{s.replace("_"," ").title()}</option>' for s in ["HOT","WARM","COLD","UNDECIDED"])}</select></div>
<div><label>Deal status</label><select name="deal_status">{''.join(f'<option value="{s}" {"selected" if review and review.deal_status==s else ""}>{s.replace("_"," ").title()}</option>' for s in ["FOLLOW_UP_REQUIRED","NEGOTIATION","INTERESTED","ALTERNATE_PROJECT_REQUIRED","BOOKING_IN_PROGRESS","BOOKED","LOST","ON_HOLD"])}</select></div>
<div><label>Quoted price / offer</label><input name="quoted_price" value="{val(review.quoted_price if review else '')}" maxlength="100"></div>
<div style="grid-column:1/-1"><label>Customer feedback after visit *</label><textarea name="customer_feedback" required>{val(review.customer_feedback if review else visit.outcome)}</textarea></div>
<div style="grid-column:1/-1"><label>Objections / reason not proceeding</label><textarea name="customer_objections">{val(review.customer_objections if review else '')}</textarea></div>
<div><label>Next follow-up date/time</label><input type="datetime-local" name="next_followup_at" value="{val(review.next_followup_at.strftime('%Y-%m-%dT%H:%M') if review and review.next_followup_at else '')}"></div>
<div><label>Next action / follow-up plan</label><input name="next_followup_plan" value="{val(review.next_followup_plan if review else visit.next_action)}" maxlength="1000" placeholder="Call, negotiation, documents, second visit..."></div>
<div><label>Show another project?</label><select name="other_project_required"><option value="no">No</option><option value="yes" {"selected" if review and review.other_project_required else ""}>Yes</option></select></div>
<div><label>Next project to show</label><select name="next_project_id"><option value="">Choose project (optional)</option>{project_opts}</select></div>
</div><p><button type="submit">Save Feedback & Next Plan</button></p></form></div></main></body></html>"""
    return HTMLResponse(body)


@router.post("/{visit_id}/feedback", dependencies=[Depends(require_csrf)])
def save_visit_feedback(
    visit_id: int, request: Request,
    status: str = Form(...), interest_level: str = Form("UNDECIDED"),
    deal_status: str = Form("FOLLOW_UP_REQUIRED"), quoted_price: str = Form(""),
    customer_feedback: str = Form(...), customer_objections: str = Form(""),
    next_followup_at: str = Form(""), next_followup_plan: str = Form(""),
    other_project_required: str = Form("no"), next_project_id: int | None = Form(None),
    csrf_token_value: str = Form("", alias="csrf_token"), db: Session = Depends(get_db),
):
    require_csrf(request, csrf_token_value)
    actor = _actor(request, db)
    if not actor or actor.role not in ALLOWED_ROLES:
        return RedirectResponse("/", status_code=303)
    visit = db.get(SiteVisit, visit_id)
    lead = db.get(Lead, visit.lead_id) if visit and visit.lead_id else None
    if not visit or not lead or not _visible_lead(actor, lead):
        return HTMLResponse("Visit not found or outside your permitted scope.", status_code=404)
    allowed_status = {"SCHEDULED","COMPLETED","RESCHEDULED","CANCELLED","NO_SHOW","CUSTOMER_NO_SHOW"}
    allowed_interest = {"HOT","WARM","COLD","UNDECIDED"}
    allowed_deal = {"FOLLOW_UP_REQUIRED","NEGOTIATION","INTERESTED","ALTERNATE_PROJECT_REQUIRED","BOOKING_IN_PROGRESS","BOOKED","LOST","ON_HOLD"}
    if status not in allowed_status or interest_level not in allowed_interest or deal_status not in allowed_deal:
        return HTMLResponse("Invalid status selection.", status_code=400)
    next_dt = None
    if next_followup_at.strip():
        try: next_dt = datetime.fromisoformat(next_followup_at)
        except ValueError: return HTMLResponse("Invalid next follow-up date/time.", status_code=400)
    if next_project_id and not db.get(Project, next_project_id):
        return HTMLResponse("Next project was not found.", status_code=400)
    review = db.scalar(select(SiteVisitReview).where(SiteVisitReview.visit_id == visit.id))
    if review is None:
        review = SiteVisitReview(visit_id=visit.id, batch_key=str(uuid4()), updated_by_id=actor.id)
        db.add(review)
    review.customer_feedback = customer_feedback.strip()
    review.interest_level = interest_level
    review.deal_status = deal_status
    review.quoted_price = quoted_price.strip() or None
    review.customer_objections = customer_objections.strip() or None
    review.next_followup_at = next_dt
    review.next_followup_plan = next_followup_plan.strip() or None
    # Make the next-step plan actionable in the existing FollowUp queue.
    if next_dt:
        followup = db.get(FollowUp, review.followup_id) if review.followup_id else None
        if followup is None:
            followup = FollowUp(
                lead_id=lead.id,
                customer_id=lead.customer_id,
                assigned_user_id=lead.assigned_user_id or actor.id,
                due_at=next_dt,
                purpose="Post-site visit follow-up",
                notes=next_followup_plan.strip() or f"Follow up after site visit #{visit.id}",
                completed=False,
            )
            db.add(followup)
            db.flush()
            review.followup_id = followup.id
        else:
            followup.due_at = next_dt
            followup.purpose = "Post-site visit follow-up"
            followup.notes = next_followup_plan.strip() or f"Follow up after site visit #{visit.id}"
            followup.completed = False
    elif review.followup_id:
        existing_followup = db.get(FollowUp, review.followup_id)
        if existing_followup and not existing_followup.completed:
            existing_followup.completed = True
    review.other_project_required = other_project_required == "yes"
    review.next_project_id = next_project_id
    review.updated_by_id = actor.id
    visit.status = status
    visit.outcome = customer_feedback.strip()
    visit.next_action = next_followup_plan.strip() or None
    db.add(AuditEvent(actor_user_id=actor.id, action="SITE_VISIT_FEEDBACK_UPDATED", entity_type="SiteVisit", entity_id=str(visit.id), details=f'{{"status":"{status}","interest_level":"{interest_level}","deal_status":"{deal_status}","next_followup_at":"{next_followup_at}","next_project_id":{next_project_id if next_project_id else "null"}}}'))
    db.commit()
    return RedirectResponse("/site-visits", status_code=303)
