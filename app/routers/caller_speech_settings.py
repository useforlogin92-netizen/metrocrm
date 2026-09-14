"""Global caller-speech voice selection controlled by Admin/Super Admin."""
from __future__ import annotations
import json
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from app.csrf import csrf_token, require_csrf_header
from app.database import get_db
from app.models import AuditEvent, User

router = APIRouter(prefix="/caller/ai-speech/settings", tags=["caller-speech-settings"])
VOICE_CATALOG = {
    "marin":{"label":"Marin — Warm Natural","style":"Warm, natural, balanced caller delivery","tone":"warm and naturally conversational"},
    "cedar":{"label":"Cedar — Calm Natural","style":"Calm, clear, trustworthy caller delivery","tone":"calm, clear and reassuring"},
    "coral":{"label":"Coral — Friendly","style":"Friendly, approachable and soft","tone":"friendly, warm and approachable"},
    "nova":{"label":"Nova — Energetic","style":"Bright, confident and engaging","tone":"confident, lively but restrained"},
    "shimmer":{"label":"Shimmer — Soft","style":"Soft, gentle and patient","tone":"soft, gentle and patient"},
    "onyx":{"label":"Onyx — Deep Professional","style":"Deeper, mature and professional","tone":"mature, grounded and professional"},
    "echo":{"label":"Echo — Clear Professional","style":"Clear, steady and businesslike","tone":"clear, steady and professional"},
    "ash":{"label":"Ash — Neutral","style":"Neutral, controlled and conversational","tone":"neutral, relaxed and conversational"},
    "sage":{"label":"Sage — Calm Consultant","style":"Measured, calm and consultant-like","tone":"calm, measured and trustworthy"},
    "verse":{"label":"Verse — Expressive","style":"Expressive, natural and engaging","tone":"expressive, natural and engaging"},
    "alloy":{"label":"Alloy — Balanced","style":"Balanced, neutral and versatile","tone":"balanced, natural and versatile"},
    "ballad":{"label":"Ballad — Warm Expressive","style":"Warm, expressive and personable","tone":"warm, expressive and personable"},
}
DEFAULT_VOICE="marin"
SETTING_ACTION="CALLER_SPEECH_VOICE_SET"

def _current_user(request: Request, db: Session):
    from app.main import _current_user as resolve_user
    return resolve_user(request, db)

def _require_admin(request: Request, db: Session):
    user=_current_user(request,db)
    if not user or user.role not in {"SUPER_ADMIN","ADMIN"}:
        raise HTTPException(status_code=403, detail="Admin or Super Admin access required")
    return user

def selected_voice(db: Session)->str:
    event=db.query(AuditEvent).filter(AuditEvent.action==SETTING_ACTION).order_by(AuditEvent.id.desc()).first()
    if event and event.details:
        try:
            voice=json.loads(event.details).get("voice")
            if voice in VOICE_CATALOG: return voice
        except (TypeError,ValueError,AttributeError): pass
    return DEFAULT_VOICE

def _instructions(voice:str)->str:
    tone=VOICE_CATALOG.get(voice,VOICE_CATALOG[DEFAULT_VOICE])["tone"]
    return (f"Speak in natural Indian Hinglish for a real-estate phone conversation. Your delivery should be {tone}. "
            "Sound like a calm, experienced Indian property consultant speaking directly to a customer, not like a presenter, announcer, audiobook or computer voice. "
            "Use a comfortable medium-slow conversational pace, realistic short pauses, subtle pitch and energy changes, and relaxed sentence endings. "
            "Give gentle emphasis to location, BHK, price and possession. Let numbers and property names land clearly. "
            "Avoid monotone, fixed rhythm, exaggerated sales energy or rushing. Use natural Indian pronunciation for Mumbai locations and real-estate terms.")

@router.get("")
def settings(request:Request, db:Session=Depends(get_db)):
    user=_current_user(request,db)
    allowed={"SUPER_ADMIN","ADMIN","MANAGER","TL","SALES_EXECUTIVE","TELECALLER"}
    if not user or user.role not in allowed: return JSONResponse({"detail":"Authentication required"},status_code=401)
    current=selected_voice(db)
    return {"voice":current,"voice_info":VOICE_CATALOG[current],"voices":[{"id":k,**v} for k,v in VOICE_CATALOG.items()],"can_manage":user.role in {"SUPER_ADMIN","ADMIN"},"csrf_token":csrf_token(request)}

@router.post("",dependencies=[Depends(require_csrf_header)])
def set_voice(payload:dict, request:Request, db:Session=Depends(get_db)):
    user=_require_admin(request,db)
    voice=str(payload.get("voice") or "").strip().lower()
    if voice not in VOICE_CATALOG: raise HTTPException(status_code=400,detail="Unsupported voice")
    details=json.dumps({"voice":voice,"label":VOICE_CATALOG[voice]["label"]})
    db.add(AuditEvent(actor_user_id=user.id,action=SETTING_ACTION,entity_type="CallerSpeechVoice",entity_id=voice,details=details))
    db.commit()
    os.environ["METROCRM_TTS_FEMALE_VOICE"]=voice
    os.environ["METROCRM_TTS_MALE_VOICE"]=voice
    return {"ok":True,"voice":voice,"voice_info":VOICE_CATALOG[voice]}

@router.post("/preview",dependencies=[Depends(require_csrf_header)])
async def preview(payload:dict, request:Request, db:Session=Depends(get_db)):
    _require_admin(request,db)
    voice=str(payload.get("voice") or "").strip().lower()
    if voice not in VOICE_CATALOG: raise HTTPException(status_code=400,detail="Unsupported voice")
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key: return JSONResponse({"detail":"AI voice is not configured"},status_code=503)
    body={"model":"gpt-4o-mini-tts","voice":voice,"input":"Namaste, main MetroCRM se baat kar raha hoon. Kandivali mein available properties mein se main aapko suitable options ki details aaram se bata sakta hoon.","instructions":_instructions(voice),"response_format":"mp3"}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response=await client.post("https://api.openai.com/v1/audio/speech",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=body)
        if response.status_code>=400: return JSONResponse({"detail":"Voice preview failed"},status_code=502)
        return Response(content=response.content,media_type="audio/mpeg",headers={"Cache-Control":"no-store"})
    except httpx.HTTPError: return JSONResponse({"detail":"AI voice service unavailable"},status_code=502)

def install_caller_voice_selection(app)->None:
    @app.middleware("http")
    async def apply_saved_caller_voice(request:Request, call_next):
        if request.url.path=="/caller/ai-speech/tts":
            try:
                db=next(get_db())
                try: voice=selected_voice(db)
                finally: db.close()
                os.environ["METROCRM_TTS_FEMALE_VOICE"]=voice
                os.environ["METROCRM_TTS_MALE_VOICE"]=voice
            except Exception: pass
        return await call_next(request)
