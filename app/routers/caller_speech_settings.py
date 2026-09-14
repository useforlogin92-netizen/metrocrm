"""Global caller-speech voice selection controlled by Admin/Super Admin."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.csrf import csrf_token, require_csrf_header
from app.database import get_db
from app.models import AuditEvent, User

router = APIRouter(prefix="/caller/ai-speech/settings", tags=["caller-speech-settings"])

VOICE_CATALOG = {
    "marin": {"label": "Marin — natural / recommended", "style": "Natural, balanced, recommended starting point"},
    "cedar": {"label": "Cedar — natural / recommended", "style": "Natural, clear, recommended starting point"},
    "coral": {"label": "Coral — warm conversational", "style": "Warm and friendly"},
    "nova": {"label": "Nova — bright conversational", "style": "Conversational and energetic"},
    "shimmer": {"label": "Shimmer — soft conversational", "style": "Soft and gentle"},
    "onyx": {"label": "Onyx — deeper professional", "style": "Deeper and professional"},
    "echo": {"label": "Echo — clear professional", "style": "Clear and steady"},
    "ash": {"label": "Ash — neutral conversational", "style": "Neutral and controlled"},
    "sage": {"label": "Sage — calm professional", "style": "Calm and measured"},
    "verse": {"label": "Verse — expressive conversational", "style": "Expressive and natural"},
    "alloy": {"label": "Alloy — balanced", "style": "Balanced general-purpose"},
    "ballad": {"label": "Ballad — expressive", "style": "Expressive and warm"},
}
DEFAULT_VOICE = "marin"
SETTING_ACTION = "CALLER_SPEECH_VOICE_SET"


def _current_user(request: Request, db: Session) -> User | None:
    from app.main import _current_user as resolve_user
    return resolve_user(request, db)


def _require_user(request: Request, db: Session) -> User:
    user = _current_user(request, db)
    if not user or user.role not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Admin or Super Admin access required")
    return user


def selected_voice(db: Session) -> str:
    event = db.query(AuditEvent).filter(AuditEvent.action == SETTING_ACTION).order_by(AuditEvent.id.desc()).first()
    if event and event.details:
        try:
            value = json.loads(event.details).get("voice")
            if value in VOICE_CATALOG:
                return value
        except (TypeError, ValueError, AttributeError):
            pass
    return DEFAULT_VOICE


@router.get("")
def caller_voice_settings(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user or user.role not in {"SUPER_ADMIN", "ADMIN", "MANAGER", "TL", "SALES_EXECUTIVE", "TELECALLER"}:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    current = selected_voice(db)
    return {
        "voice": current,
        "voice_info": VOICE_CATALOG[current],
        "voices": [{"id": key, **value} for key, value in VOICE_CATALOG.items()],
        "can_manage": user.role in {"SUPER_ADMIN", "ADMIN"},
        "csrf_token": csrf_token(request),
    }


@router.post("", dependencies=[Depends(require_csrf_header)])
def set_caller_voice(payload: dict, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    voice = str(payload.get("voice") or "").strip().lower()
    if voice not in VOICE_CATALOG:
        raise HTTPException(status_code=400, detail="Unsupported voice")
    db.add(
        AuditEvent(
            actor_user_id=user.id,
            action=SETTING_ACTION,
            entity_type="CallerSpeechVoice",
            entity_id=voice,
            details=json.dumps({"voice": voice, "label": VOICE_CATALOG[voice]["label"]}),
        )
    )
    db.commit()
    os.environ["METROCRM_TTS_FEMALE_VOICE"] = voice
    os.environ["METROCRM_TTS_MALE_VOICE"] = voice
    return {"ok": True, "voice": voice, "voice_info": VOICE_CATALOG[voice]}


def install_caller_voice_selection(app) -> None:
    @app.middleware("http")
    async def apply_saved_caller_voice(request: Request, call_next):
        if request.url.path == "/caller/ai-speech/tts":
            try:
                db = next(get_db())
                try:
                    voice = selected_voice(db)
                finally:
                    db.close()
                os.environ["METROCRM_TTS_FEMALE_VOICE"] = voice
                os.environ["METROCRM_TTS_MALE_VOICE"] = voice
            except Exception:
                pass
        return await call_next(request)
