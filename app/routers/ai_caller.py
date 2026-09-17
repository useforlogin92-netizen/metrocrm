"""Secure adapter endpoints for external AI/auto-caller providers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Lead, User
from app.services.ai_caller import build_context, execute_tool, provider_configured, system_prompt, tool_definitions

router = APIRouter(prefix="/api/ai-caller", tags=["ai-caller"])
_ALLOWED = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}
_PROVIDER_TOKEN_TTL = 10 * 60


def _user(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _b64_json(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _provider_token(lead_id: int, now: int | None = None) -> str:
    """Mint a short-lived, lead-bound provider credential."""
    secret = settings.ai_caller_provider_secret
    if not secret:
        raise ValueError("AI caller provider credential is not configured")
    issued = int(time.time() if now is None else now)
    payload = {"v": 1, "lead_id": int(lead_id), "iat": issued, "exp": issued + _PROVIDER_TOKEN_TTL}
    encoded = _b64_json(payload)
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"v1.{encoded}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _provider_claims(token: str | None, lead_id: int, now: int | None = None) -> dict | None:
    """Validate a short-lived provider credential and its lead binding."""
    secret = settings.ai_caller_provider_secret
    if not secret or not token:
        return None
    try:
        version, encoded, supplied_signature = token.split(".", 2)
        if version != "v1":
            return None
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(supplied_signature + "=" * (-len(supplied_signature) % 4))
        if not hmac.compare_digest(supplied, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        current = int(time.time() if now is None else now)
        if int(payload.get("v", 0)) != 1 or int(payload.get("lead_id", -1)) != int(lead_id):
            return None
        if int(payload.get("exp", 0)) <= current or int(payload.get("iat", 0)) > current + 30:
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _lead_in_scope(user: User, lead: Lead, db: Session) -> bool:
    """Keep authenticated AI caller context within the user's lead ownership tree."""
    if user.role in {"SUPER_ADMIN", "ADMIN"}:
        return True
    if lead.assigned_user_id == user.id:
        return True
    if user.role not in {"MANAGER", "TL"}:
        return False
    ids = {user.id}
    changed = True
    while changed:
        changed = False
        children = db.scalars(select(User).where(User.reporting_manager_id.in_(ids))).all()
        for child in children:
            if child.id not in ids:
                ids.add(child.id)
                changed = True
    return lead.assigned_user_id in ids


def _context_payload(db: Session, lead_id: int) -> dict:
    context = build_context(db, lead_id)
    return {"system_prompt": system_prompt(), "context": context, "tools": tool_definitions(), "voice": {"language": settings.ai_caller_default_language, "male_voice": settings.ai_caller_male_voice, "female_voice": settings.ai_caller_female_voice, "style": "warm Indian conversational"}}


@router.get("/config")
def ai_caller_config(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user or user.role not in _ALLOWED:
        return RedirectResponse("/", status_code=303)
    return {"provider": settings.ai_caller_provider or "none", "configured": provider_configured(), "languages": ["hi-IN", "en-IN", "hinglish"], "male_voice": settings.ai_caller_male_voice or None, "female_voice": settings.ai_caller_female_voice or None}


@router.post("/provider-token/{lead_id}")
def issue_provider_token(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """Issue a short-lived credential for exactly one lead after CRM RBAC checks."""
    user = _user(request, db)
    if not user or user.role not in _ALLOWED:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    lead = db.get(Lead, lead_id)
    if not lead or not _lead_in_scope(user, lead, db):
        return JSONResponse({"detail": "Lead not found"}, status_code=404)
    try:
        return {"token": _provider_token(lead_id), "expires_in": _PROVIDER_TOKEN_TTL, "lead_id": lead_id}
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)


def _provider_lead(lead_id: int, token: str | None, db: Session) -> tuple[Lead | None, JSONResponse | None]:
    """Validate credential and lead existence without exposing existence to unauthenticated callers."""
    if _provider_claims(token, lead_id) is None:
        return None, JSONResponse({"detail": "Invalid or unscoped AI caller credential"}, status_code=401)
    lead = db.get(Lead, lead_id)
    if lead is None:
        return None, JSONResponse({"detail": "Lead not found"}, status_code=404)
    return lead, None


@router.get("/leads/{lead_id}/context")
def ai_caller_context(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user or user.role not in _ALLOWED:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    lead = db.get(Lead, lead_id)
    if not lead or not _lead_in_scope(user, lead, db):
        return JSONResponse({"detail": "Lead not found"}, status_code=404)
    try:
        return _context_payload(db, lead_id)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)


@router.get("/provider/leads/{lead_id}/context")
def provider_context(lead_id: int, x_ai_caller_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    lead, error = _provider_lead(lead_id, x_ai_caller_token, db)
    if error:
        return error
    try:
        return _context_payload(db, lead.id)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)


@router.post("/provider/leads/{lead_id}/tool")
def provider_tool(lead_id: int, payload: dict, x_ai_caller_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    lead, error = _provider_lead(lead_id, x_ai_caller_token, db)
    if error:
        return error
    tool = str(payload.get("tool") or "").strip()
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict) or not tool:
        return JSONResponse({"detail": "Invalid tool request"}, status_code=400)
    try:
        return execute_tool(db, lead.id, tool, arguments)
    except (ValueError, TypeError, KeyError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/provider/leads/{lead_id}/event")
def provider_event(lead_id: int, payload: dict, x_ai_caller_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    lead, error = _provider_lead(lead_id, x_ai_caller_token, db)
    if error:
        return error
    # Deliberately store only bounded metadata by default; full transcripts remain with the voice provider unless enabled.
    from app.models import AuditEvent
    event = AuditEvent(actor_user_id=None, action="AI_CALL_EVENT", entity_type="Lead", entity_id=str(lead.id), details=json.dumps({"event": str(payload.get("event") or "UNKNOWN")[:80], "call_id": str(payload.get("call_id") or "")[:160], "summary": str(payload.get("summary") or "")[:4000], "store_transcript": bool(settings.ai_caller_store_transcript and payload.get("transcript"))}, ensure_ascii=False))
    db.add(event)
    db.commit()
    return {"ok": True}
