"""Secure adapter endpoints for external AI/auto-caller providers."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.services.ai_caller import build_context, execute_tool, provider_configured, system_prompt, tool_definitions

router = APIRouter(prefix="/api/ai-caller", tags=["ai-caller"])
_ALLOWED = {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}


def _user(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


def _provider_ok(token: str | None) -> bool:
    secret = settings.ai_caller_provider_secret
    return bool(secret and token and hmac.compare_digest(token, secret))


def _context_payload(db: Session, lead_id: int) -> dict:
    context = build_context(db, lead_id)
    return {"system_prompt": system_prompt(), "context": context, "tools": tool_definitions(), "voice": {"language": settings.ai_caller_default_language, "male_voice": settings.ai_caller_male_voice, "female_voice": settings.ai_caller_female_voice, "style": "warm Indian conversational"}}


@router.get("/config")
def ai_caller_config(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user or user.role not in _ALLOWED:
        return RedirectResponse("/", status_code=303)
    return {"provider": settings.ai_caller_provider or "none", "configured": provider_configured(), "languages": ["hi-IN", "en-IN", "hinglish"], "male_voice": settings.ai_caller_male_voice or None, "female_voice": settings.ai_caller_female_voice or None}


@router.get("/leads/{lead_id}/context")
def ai_caller_context(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user or user.role not in _ALLOWED:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    try:
        return _context_payload(db, lead_id)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)


@router.get("/provider/leads/{lead_id}/context")
def provider_context(lead_id: int, x_ai_caller_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not _provider_ok(x_ai_caller_token):
        return JSONResponse({"detail": "Invalid AI caller credential"}, status_code=401)
    try:
        return _context_payload(db, lead_id)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)


@router.post("/provider/leads/{lead_id}/tool")
def provider_tool(lead_id: int, payload: dict, x_ai_caller_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not _provider_ok(x_ai_caller_token):
        return JSONResponse({"detail": "Invalid AI caller credential"}, status_code=401)
    tool = str(payload.get("tool") or "").strip()
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict) or not tool:
        return JSONResponse({"detail": "Invalid tool request"}, status_code=400)
    try:
        return execute_tool(db, lead_id, tool, arguments)
    except (ValueError, TypeError, KeyError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/provider/leads/{lead_id}/event")
def provider_event(lead_id: int, payload: dict, x_ai_caller_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not _provider_ok(x_ai_caller_token):
        return JSONResponse({"detail": "Invalid AI caller credential"}, status_code=401)
    # Deliberately store only bounded metadata by default; full transcripts remain with the voice provider unless enabled.
    from app.models import AuditEvent
    event = AuditEvent(actor_user_id=None, action="AI_CALL_EVENT", entity_type="Lead", entity_id=str(lead_id), details=json.dumps({"event": str(payload.get("event") or "UNKNOWN")[:80], "call_id": str(payload.get("call_id") or "")[:160], "summary": str(payload.get("summary") or "")[:4000], "store_transcript": bool(settings.ai_caller_store_transcript and payload.get("transcript"))}, ensure_ascii=False))
    db.add(event)
    db.commit()
    return {"ok": True}
