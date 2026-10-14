"""Mock-first softphone and guarded provider callbacks for MetroCRM."""
from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cloud_calling_models import CloudCallLog, CloudCallProviderLink
from app.config import settings
from app.csrf import csrf_token, require_csrf_header
from app.database import get_db
from app.models import Customer, Lead, User
from app.telephony.exotel import (
    TelephonyNotConfigured, TelephonyProviderError, initiate_call,
)

router = APIRouter(prefix="/caller", tags=["cloud-calling"])
ALLOWED_ROLES = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}
ACTIVE_STATUSES = {"initiated", "ringing", "in_progress"}
TERMINAL_STATUSES = {"completed", "missed", "failed", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        "status": call.status, "phone_number": call.phone_number, "provider": call.provider,
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
    provider = (settings.cloud_calling_provider or "mock").strip().lower()
    live = provider == "exotel"
    banner = "Exotel live mode selected; calls require complete provider configuration." if live else "Mock mode — no real phone call is placed."
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MetroCRM Cloud Dialer</title><link rel="stylesheet" href="/static/cloud-dialer.css"></head><body><main class="dialer-page"><h1>MetroCRM Cloud Dialer</h1><p class="mock-banner">{banner}</p><section id="cloud-dialer" data-provider="{provider}" data-csrf="{token}"></section><p><a href="/caller/leads">Back to Leads</a></p></main><script src="/static/cloud-dialer.js" defer></script></body></html>""")


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

    provider = (settings.cloud_calling_provider or "mock").strip().lower()
    if provider not in {"mock", "exotel"}:
        raise HTTPException(status_code=503, detail="cloud_calling_provider_unsupported")
    now = _now()
    call = CloudCallLog(
        id=str(uuid4()), lead_id=lead.id if lead else None, customer_id=customer_id,
        agent_user_id=user.id, call_type="outbound",
        status="ringing" if provider == "mock" else "initiated",
        phone_number=phone, provider=provider, started_at=now, created_at=now, updated_at=now,
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    if provider == "exotel":
        base_url = settings.cloud_calling_public_base_url.strip().rstrip("/")
        callback_secret = settings.exotel_status_callback_secret.strip()
        if not base_url.startswith("https://") or len(callback_secret) < 32:
            call.status = "failed"
            call.ended_at = _now()
            call.updated_at = _now()
            db.commit()
            raise HTTPException(status_code=503, detail="exotel_callback_configuration_incomplete")
        callback_url = f"{base_url}/caller/api/telephony/exotel/status?token={callback_secret}"
        try:
            provider_call = initiate_call(phone, status_callback=callback_url)
            link = CloudCallProviderLink(
                id=str(uuid4()), call_id=call.id, provider="exotel",
                provider_call_id=provider_call.provider_call_id,
            )
            db.add(link)
            provider_status = _map_provider_status(provider_call.status)
            call.status = provider_status or "initiated"
            call.updated_at = _now()
            if call.status in TERMINAL_STATUSES:
                call.ended_at = call.updated_at
            db.commit()
            db.refresh(call)
        except (TelephonyNotConfigured, TelephonyProviderError, ValueError):
            db.rollback()
            failed = db.get(CloudCallLog, call.id)
            if failed:
                failed.status = "failed"
                failed.ended_at = _now()
                failed.updated_at = failed.ended_at
                db.commit()
            raise HTTPException(status_code=502, detail="exotel_call_request_failed")
    return _serialize(call)


@router.post("/api/telephony/exotel/status", include_in_schema=False)
async def exotel_status_callback(request: Request, token: str, db: Session = Depends(get_db)):
    """Public provider webhook authenticated with a high-entropy shared secret."""
    expected = settings.exotel_status_callback_secret.strip()
    if len(expected) < 32 or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="invalid_provider_callback_auth")
    raw = await request.body()
    try:
        if "application/json" in request.headers.get("content-type", "").lower():
            payload = json.loads(raw.decode("utf-8"))
        else:
            parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            payload = {key: values[-1] for key, values in parsed.items()}
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="invalid_callback_payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_callback_payload")
    nested = payload.get("Call")
    if isinstance(nested, dict):
        payload = {**nested, **payload}
    provider_call_id = str(payload.get("CallSid") or payload.get("Sid") or "").strip()
    if not provider_call_id or len(provider_call_id) > 128:
        raise HTTPException(status_code=400, detail="provider_call_id_required")
    link = db.scalar(select(CloudCallProviderLink).where(
        CloudCallProviderLink.provider == "exotel",
        CloudCallProviderLink.provider_call_id == provider_call_id,
    ))
    if link is None:
        # Provider retries can race with initial persistence; 404 asks provider to retry.
        raise HTTPException(status_code=404, detail="provider_call_not_found")
    call = db.get(CloudCallLog, link.call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="crm_call_not_found")

    status = _map_provider_status(str(payload.get("Status") or ""))
    event = str(payload.get("EventType") or "").strip().lower()[:32] or None
    if status:
        # Do not let delayed intermediate callbacks reopen a completed call.
        if call.status not in TERMINAL_STATUSES or status in TERMINAL_STATUSES:
            call.status = status
        now = _now()
        if event == "answered" and call.answered_at is None:
            call.answered_at = now
            if call.status not in TERMINAL_STATUSES:
                call.status = "in_progress"
        if status in TERMINAL_STATUSES:
            call.ended_at = now
            duration = payload.get("ConversationDuration") or payload.get("Duration")
            try:
                call.duration_seconds = max(0, min(int(float(duration)), 86400)) if duration not in (None, "", "null") else call.duration_seconds
            except (TypeError, ValueError, OverflowError):
                pass
        call.updated_at = now
    link.last_event = event or status or link.last_event
    link.updated_at = _now()
    db.commit()
    return {"received": True}


def _map_provider_status(value: str) -> str | None:
    status = value.strip().lower().replace("_", "-")
    return {
        "queued": "initiated", "initiated": "initiated",
        "ringing": "ringing", "in-progress": "in_progress", "answered": "in_progress",
        "completed": "completed", "failed": "failed", "busy": "missed",
        "no-answer": "missed", "cancelled": "cancelled", "canceled": "cancelled",
    }.get(status)


@router.post("/api/calls/incoming", dependencies=[Depends(require_csrf_header)])
def simulate_incoming(request: Request, db: Session = Depends(get_db)):
    """Authenticated demo-only incoming-call simulation; no public inbound routing."""
    user = _require_user(request, db)
    if (settings.cloud_calling_provider or "mock").strip().lower() != "mock":
        raise HTTPException(status_code=409, detail="incoming_simulation_only_available_in_mock_mode")
    now = _now()
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
    if call.provider != "mock":
        if payload.notes is not None:
            call.notes = payload.notes.strip() or None
            call.updated_at = _now()
            db.commit()
            db.refresh(call)
            return _serialize(call)
        raise HTTPException(status_code=409, detail="provider_controls_not_configured")
    now = _now()
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
