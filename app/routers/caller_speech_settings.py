"""Admin-controlled caller-speech voice profiles and natural playback settings."""
from __future__ import annotations
import json
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from app.csrf import csrf_token, require_csrf_header
from app.database import get_db
from app.models import AuditEvent
router=APIRouter(prefix="/caller/ai-speech/settings",tags=["caller-speech-settings"])
VOICE_CATALOG={
 "marin":{"label":"Marin — Warm Natural","style":"Warm, natural and balanced"},"cedar":{"label":"Cedar — Calm Natural","style":"Calm, clear and reassuring"},"coral":{"label":"Coral — Friendly Female-style","style":"Friendly, soft and approachable"},"nova":{"label":"Nova — Bright Natural","style":"Bright, confident and engaging"},"shimmer":{"label":"Shimmer — Soft Female-style","style":"Soft, gentle and patient"},"onyx":{"label":"Onyx — Deep Male-style","style":"Deep, mature and professional"},"echo":{"label":"Echo — Clear Male-style","style":"Clear, steady and businesslike"},"ash":{"label":"Ash — Neutral Natural","style":"Neutral, relaxed and conversational"},"sage":{"label":"Sage — Calm Consultant","style":"Measured, calm and trustworthy"},"verse":{"label":"Verse — Expressive Natural","style":"Expressive, natural and engaging"},"alloy":{"label":"Alloy — Balanced","style":"Balanced, natural and versatile"},"ballad":{"label":"Ballad — Warm Expressive","style":"Warm, expressive and personable"},}
DEFAULT_FEMALE="coral"; DEFAULT_MALE="onyx"; SETTING_ACTION="CALLER_SPEECH_VOICE_SET"
def _current_user(request:Request,db:Session):
    from app.main import _current_user as resolve_user
    return resolve_user(request,db)
def _require_admin(request:Request,db:Session):
    user=_current_user(request,db)
    if not user or user.role not in {"SUPER_ADMIN","ADMIN"}: raise HTTPException(status_code=403,detail="Admin or Super Admin access required")
    return user
def selected_voices(db:Session)->dict[str,str]:
    result={"female":DEFAULT_FEMALE,"male":DEFAULT_MALE}; seen=set()
    events=db.query(AuditEvent).filter(AuditEvent.action==SETTING_ACTION).order_by(AuditEvent.id.desc()).all()
    for event in events:
        if not event.details: continue
        try:
            data=json.loads(event.details); gender=str(data.get("gender") or "").lower(); voice=str(data.get("voice") or "").lower()
            if gender in result and gender not in seen and voice in VOICE_CATALOG:
                result[gender]=voice; seen.add(gender)
                if len(seen)==2: break
        except (TypeError,ValueError,AttributeError): pass
    return result
def selected_voice(db:Session,gender:str="female")->str:return selected_voices(db).get(gender,DEFAULT_FEMALE)
def _instructions(voice:str,gender:str)->str:
    style=VOICE_CATALOG.get(voice,VOICE_CATALOG[DEFAULT_FEMALE])["style"]; gender_style="a natural Indian female consultant" if gender=="female" else "a natural Indian male consultant"
    return (f"Speak as {gender_style} on a real-estate phone call. The voice character should be {style}. Sound warm, relaxed, attentive and genuinely conversational, never like an announcer, presenter, audiobook or computer. Use a noticeably relaxed medium-slow pace. Leave small natural pauses between thoughts and after important property details. Use subtle pitch and energy changes, gentle emphasis on location, BHK, price and possession, and relaxed sentence endings. Do not rush through lists. Do not use a fixed rhythm, monotone delivery, exaggerated sales enthusiasm or artificial cheerfulness. Pronounce Mumbai locations and Indian real-estate terms naturally and clearly.")
@router.get("")
def settings(request:Request,db:Session=Depends(get_db)):
    user=_current_user(request,db); allowed={"SUPER_ADMIN","ADMIN","MANAGER","TL","SALES_EXECUTIVE","TELECALLER"}
    if not user or user.role not in allowed:return JSONResponse({"detail":"Authentication required"},status_code=401)
    voices=selected_voices(db); return {"voices_selected":voices,"voice":voices["female"],"voice_info":VOICE_CATALOG[voices["female"]],"voices":[{"id":k,**v} for k,v in VOICE_CATALOG.items()],"can_manage":user.role in {"SUPER_ADMIN","ADMIN"},"speech_speed":0.86,"csrf_token":csrf_token(request)}
@router.post("",dependencies=[Depends(require_csrf_header)])
def set_caller_voice(payload:dict,request:Request,db:Session=Depends(get_db)):
    user=_require_admin(request,db); gender=str(payload.get("gender") or "female").strip().lower(); voice=str(payload.get("voice") or "").strip().lower()
    if gender not in {"female","male"}:raise HTTPException(status_code=400,detail="Gender profile must be female or male")
    if voice not in VOICE_CATALOG:raise HTTPException(status_code=400,detail="Unsupported voice")
    db.add(AuditEvent(actor_user_id=user.id,action=SETTING_ACTION,entity_type="CallerSpeechVoice",entity_id=f"{gender}:{voice}",details=json.dumps({"gender":gender,"voice":voice,"label":VOICE_CATALOG[voice]["label"]}))); db.commit()
    if gender=="female":os.environ["METROCRM_TTS_FEMALE_VOICE"]=voice
    else:os.environ["METROCRM_TTS_MALE_VOICE"]=voice
    return {"ok":True,"gender":gender,"voice":voice,"voice_info":VOICE_CATALOG[voice],"voices_selected":selected_voices(db)}
@router.post("/preview",dependencies=[Depends(require_csrf_header)])
async def preview(payload:dict,request:Request,db:Session=Depends(get_db)):
    _require_admin(request,db); gender=str(payload.get("gender") or "female").strip().lower(); voice=str(payload.get("voice") or "").strip().lower()
    if gender not in {"female","male"} or voice not in VOICE_CATALOG:raise HTTPException(status_code=400,detail="Invalid voice profile")
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:return JSONResponse({"detail":"AI voice is not configured"},status_code=503)
    body={"model":"gpt-4o-mini-tts","voice":voice,"input":"Namaste, main MetroCRM se baat kar raha hoon. Aapki requirement ke hisaab se Kandivali aur Andheri mein kuch suitable property options hain. Main aapko ek-ek karke clear details bata deta hoon.","instructions":_instructions(voice,gender),"speed":0.86,"response_format":"mp3"}
    try:
        async with httpx.AsyncClient(timeout=45) as client:response=await client.post("https://api.openai.com/v1/audio/speech",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=body)
        if response.status_code>=400:return JSONResponse({"detail":"Voice preview failed"},status_code=502)
        return Response(content=response.content,media_type="audio/mpeg",headers={"Cache-Control":"no-store"})
    except httpx.HTTPError:return JSONResponse({"detail":"AI voice service unavailable"},status_code=502)
def install_caller_voice_selection(app)->None:
    @app.middleware("http")
    async def apply_saved_caller_voice(request:Request,call_next):
        if request.url.path=="/caller/ai-speech/tts":
            try:
                db=next(get_db())
                try:voices=selected_voices(db)
                finally:db.close()
                os.environ["METROCRM_TTS_FEMALE_VOICE"]=voices["female"]; os.environ["METROCRM_TTS_MALE_VOICE"]=voices["male"]
            except Exception:pass
        return await call_next(request)
