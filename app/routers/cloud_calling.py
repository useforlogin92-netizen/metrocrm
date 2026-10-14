"""Mock-first in-app softphone endpoints for the existing FastAPI CRM."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cloud_calling_models import CloudCallLog
from app.csrf import csrf_token, require_csrf_header
from app.database import get_db
from app.models import Customer, Lead, User

router = APIRouter(prefix="/caller", tags=["mock-cloud-calling"])
ALLOWED_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}
ACTIVE_STATUSES = {"initiated", "ringing", "in_progress"}


def _user(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _can_access_lead(user: User, lead: Lead, db: Session) -> bool:
    if user.role in {"SUPER_ADMIN", "ADMIN"} or lead.assigned_user_id == user.id:
        return True
    if user.role not in {"MANAGER", "TL"}:
        return False
    visible = {user.id}
    frontier = {user.id}
    while frontier:
        children = db.scalars(select(User.id).where(User.reporting_manager_id.in_(frontier))).all()
        frontier = {int(uid) for uid in children if int(uid) not in visible}
        visible.update(frontier)
    return lead.assigned_user_id in visible


def _require_user(request: Request, db: Session) -> User:
    user = _user(request, db)
    if not user or user.role not in ALLOWED_ROLES or not user.is_active:
        raise HTTPException(status_code=403, detail="caller_access_required")
    return user


class StartCall(BaseModel):
    phone_number: str = Field(min_length=7, max_length=30)
    lead_id: int | None = None
    customer_id: int | None = None


class UpdateCall(BaseModel):
    action: str = Field(pattern="^(answer|mute|unmute|hold|resume|end|fail|miss)$")
    notes: str | None = Field(default=None, max_length=4000)


def _serialize(call: CloudCallLog) -> dict:
    return {
        "id": call.id, "lead_id": call.lead_id, "customer_id": call.customer_id,
        "agent_user_id": call.agent_user_id, "call_type": call.call_type,
        "status": call.status, "phone_number": call.phone_number, "provider": "mock",
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "answered_at": call.answered_at.isoformat() if call.answered_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": call.duration_seconds, "notes": call.notes,
    }


@router.get("/softphone", response_class=HTMLResponse, include_in_schema=False)
def softphone_page(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user or user.role not in ALLOWED_ROLES or not user.is_active:
        return RedirectResponse("/", status_code=303)
    token = csrf_token(request)
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MetroCRM Mock Softphone</title><link rel="stylesheet" href="/static/cloud-dialer.css"></head><body><main class="dialer-page"><h1>MetroCRM Cloud Dialer</h1><p class="mock-banner">Mock mode — no real phone call is placed.</p><section id="cloud-dialer" data-csrf="{token}"></section><p><a href="/caller/leads">Back to Leads</a></p></main><script src="/static/cloud-dialer.js" defer></script></body></html>""")


@router.post("/api/calls", dependencies=[Depends(require_csrf_header)])
def start_call(payload: StartCall, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    phone = "".join(ch for ch in payload.phone_number.strip() if ch.isdigit() or ch == "+")
    if len("".join(ch for ch in phone if ch.isdigit())) < 7:
        raise HTTPException(status_code=422, detail="valid_phone_number_required")
    lead = db.get(Lead, payload.lead_id) if payload.lead_id is not None else None
    if payload.lead_id is not None and (lead is None or not _can_access_lead(user, lead, db)):
        raise HTTPException(status_code=404, detail="lead_not_found")
    customer_id = payload.customer_id or (lead.customer_id if lead else None)
    if customer_id is not None and db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail="customer_not_found")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    call = CloudCallLog(id=str(uuid4()), lead_id=lead.id if lead else None, customer_id=customer_id,
                        agent_user_id=user.id, call_type="outbound", status="ringing",
                        phone_number=phone, provider="mock", started_at=now, created_at=now, updated_at=now)
    db.add(call)
    db.commit()
    db.refresh(call)
    return _serialize(call)


@router.post("/api/calls/incoming", dependencies=[Depends(require_csrf_header)])
def simulate_incoming(request: Request, db: Session = Depends(get_db)):
    """Authenticated demo-only incoming-call simulation; no public webhook."""
    user = _require_user(request, db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    call = CloudCallLog(id=str(uuid4()), agent_user_id=user.id, call_type="inbound",
                        status="ringing", phone_number="MOCK-INCOMING", provider="mock",
                        started_at=now, created_at=now, updated_at=now)
    db.add(call)
    db.commit()
    db.refresh(call)
    return _serialize(call)


@router.patch("/api/calls/{call_id}", dependencies=[Depends(require_csrf_header)])
def update_call(call_id: str, payload: UpdateCall, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    call = db.get(CloudCallLog, call_id)
    if not call or (call.agent_user_id != user.id and user.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL"}):
        raise HTTPException(status_code=404, detail="call_not_found")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if payload.action == "answer":
        if call.status != "ringing":
            raise HTTPException(status_code=409, detail="call_not_ringing")
        call.status = "in_progress"
        call.answered_at = now
    elif payload.action in {"end", "fail", "miss"}:
        if call.status not in ACTIVE_STATUSES:
            raise HTTPException(status_code=409, detail="call_already_ended")
        call.status = {"end": "completed", "fail": "failed", "miss": "missed"}[payload.action]
        call.ended_at = now
        call.duration_seconds = max(0, int((now - (call.answered_at or call.started_at)).total_seconds()))
    elif payload.action in {"mute", "unmute", "hold", "resume"}:
        if call.status != "in_progress":
            raise HTTPException(status_code=409, detail="call_not_in_progress")
    if payload.notes is not None:
        call.notes = payload.notes.strip() or None
    call.updated_at = now
    db.commit()
    db.refresh(call)
    return _serialize(call)


@router.get("/api/calls")
def list_calls(request: Request, db: Session = Depends(get_db), limit: int = 50):
    user = _require_user(request, db)
    limit = max(1, min(limit, 100))
    query = select(CloudCallLog).order_by(CloudCallLog.created_at.desc()).limit(limit)
    if user.role not in {"SUPER_ADMIN", "ADMIN"}:
        query = query.where(CloudCallLog.agent_user_id == user.id)
    return {"calls": [_serialize(call) for call in db.scalars(query).all()]}
