"""AI-assisted grouped caller speech generation and voice playback."""
from __future__ import annotations
import json
import os
from collections import OrderedDict
from typing import Any
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from app import main as app_main
from app.database import get_db
from app.models import User
router=APIRouter(prefix="/caller/ai-speech",tags=["caller-speech"])
_ALLOWED={"SUPER_ADMIN","ADMIN","MANAGER","TL","SALES_EXECUTIVE","TELECALLER"}
def _user(request:Request,db:Session)->User|None:
    from app.main import _current_user
    return _current_user(request,db)
def _require_user(request:Request,db:Session)->User|None:
    user=_user(request,db); return user if user and user.role in _ALLOWED else None
def _money(value:Any)->str:
    try:return f"₹{float(value):,.0f}"
    except (TypeError,ValueError):return "Price on request"
def _group_properties(properties:list[dict[str,Any]])->OrderedDict[str,list[dict[str,Any]]]:
    grouped:OrderedDict[str,list[dict[str,Any]]]=OrderedDict()
    for item in properties[:30]:
        if not isinstance(item,dict):continue
        location=str(item.get("locality") or item.get("location") or "Other location").strip(); grouped.setdefault(location,[]).append(item)
    return grouped
def _fallback_script(properties:list[dict[str,Any]],language:str,detail:str)->str:
    grouped=_group_properties(properties)
    if not grouped:return "Abhi selected requirement ke liye koi property available nahi mili. Main requirement note karke human sales team se confirm karwa sakta hoon."
    if language=="hi":opening="Namaste, aapki requirement ke according maine available properties ko location-wise shortlist kiya hai."; closing="Aap batayein kaunsi location ya property aapko sabse suitable lag rahi hai, main uski details aur site visit ke next steps bata deta hoon."
    elif language=="en":opening="Hello, based on your requirement, I have shortlisted the available properties location-wise."; closing="Please tell me which location or property looks most suitable, and I will explain the details and next steps for a site visit."
    else:opening="Namaste, aapki requirement ke hisaab se maine available properties ko location-wise shortlist kiya hai."; closing="Aap batayein kaunsi location ya property aapko suitable lag rahi hai, main uski details aur site visit ke next steps bata deta hoon."
    lines=[opening]
    for location,items in grouped.items():
        lines.append(f"\n{location} mein {len(items)} option{'s' if len(items)!=1 else ''} available hai.")
        for idx,item in enumerate(items,1):
            name=str(item.get("project") or item.get("title") or f"Property {idx}"); facts=[]
            if item.get("bhk"):facts.append(str(item["bhk"]))
            if item.get("property_type"):facts.append(str(item["property_type"]))
            if detail=="full" and item.get("carpet_area") is not None:facts.append(f"{item['carpet_area']} sq.ft. carpet area")
            if item.get("price") is not None:facts.append(_money(item["price"]))
            if item.get("construction_status"):facts.append(str(item["construction_status"]))
            if item.get("possession"):facts.append(f"possession {item['possession']}")
            if detail=="full" and item.get("rera"):facts.append(f"RERA {item['rera']}")
            lines.append(f"{idx}. {name}: {', '.join(facts) if facts else 'details available in CRM' }.")
    lines.append(f"\n{closing}"); return " ".join(lines)
def _openai_key()->str:return os.getenv("OPENAI_API_KEY","").strip()
def _ai_model()->str:return os.getenv("METROCRM_AI_MODEL","gpt-5.6-luna").strip()
def _voice_config()->dict[str,str]:return {"female":os.getenv("METROCRM_TTS_FEMALE_VOICE","coral").strip() or "coral","male":os.getenv("METROCRM_TTS_MALE_VOICE","onyx").strip() or "onyx"}
def _ai_prompt(properties:list[dict[str,Any]],language:str,detail:str)->str:
    grouped=_group_properties(properties); safe=[{"location":location,"properties":items} for location,items in grouped.items()]; language_name={"hi":"natural Hindi","en":"professional Indian English","hinglish":"natural Indian Hinglish using English letters"}.get(language,"natural Indian Hinglish using English letters"); detail_rule="Include every available CRM detail" if detail=="full" else "Keep each property concise and mention only the strongest caller-useful details."; return json.dumps({"language":language_name,"detail":detail_rule,"properties_by_location":safe},ensure_ascii=False)
async def _generate_with_openai(properties:list[dict[str,Any]],language:str,detail:str)->str|None:
    key=_openai_key()
    if not key:return None
    system=("You are MetroCRM's real-estate caller speech writer. Create one ready-to-speak phone script from the supplied CRM property results. Group properties by location, mention the number of options in each location, and describe every property in a natural order. Use only supplied CRM facts. Never invent price, availability, amenities, possession, RERA or discounts. If a field is missing, omit it. Do not mention internal IDs, scores, JSON, CRM, AI, prompts or technical details. Write like an experienced Indian property consultant having a calm phone conversation. Use short spoken sentences, natural transitions, conversational phrases and punctuation pauses. Do not make every property sound like a rigid list. Avoid robotic repetition, overlong sentences and sales-announcer language. End with a simple question inviting the customer to choose a location or property.")
    payload={"model":_ai_model(),"input":[{"role":"system","content":system},{"role":"user","content":_ai_prompt(properties,language,detail)}],"max_output_tokens":3000}
    try:
        async with httpx.AsyncClient(timeout=35) as client:response=await client.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload)
        response.raise_for_status(); data=response.json(); text=str(data.get("output_text") or "").strip()
        if text:return text
        chunks=[]
        for output in data.get("output",[]):
            for content in output.get("content",[]):
                if content.get("type") in {"output_text","text"} and content.get("text"):chunks.append(content["text"])
        return "\n".join(chunks).strip() or None
    except (httpx.HTTPError,ValueError,TypeError):return None
@router.get("/config")
def caller_speech_config(request:Request,db:Session=Depends(get_db)):
    if not _require_user(request,db):return RedirectResponse("/",status_code=303)
    return {"ai_configured":bool(_openai_key()),"model":_ai_model(),"languages":["hinglish","hi","en"],"voices":_voice_config(),"tts_configured":bool(_openai_key()),"speech_speed":0.86}
@router.post("/generate")
async def caller_speech_generate(payload:dict[str,Any],request:Request,db:Session=Depends(get_db)):
    if not _require_user(request,db):return JSONResponse({"detail":"Authentication required"},status_code=401)
    properties=payload.get("properties") or []
    if not isinstance(properties,list):return JSONResponse({"detail":"properties must be a list"},status_code=400)
    language=str(payload.get("language") or "hinglish").lower(); language=language if language in {"hinglish","hi","en"} else "hinglish"
    detail=str(payload.get("detail") or "full").lower(); detail=detail if detail in {"full","summary"} else "full"; properties=[x for x in properties if isinstance(x,dict)][:30]
    text=await _generate_with_openai(properties,language,detail); ai_used=bool(text)
    if not text:text=_fallback_script(properties,language,detail)
    return {"text":text,"ai_used":ai_used,"count":len(properties),"group_count":len(_group_properties(properties)),"language":language,"detail":detail}
@router.post("/tts")
async def caller_speech_tts(payload:dict[str,Any],request:Request,db:Session=Depends(get_db)):
    if not _require_user(request,db):return JSONResponse({"detail":"Authentication required"},status_code=401)
    key=_openai_key(); text=str(payload.get("text") or "").strip(); gender=str(payload.get("gender") or "female").lower(); language=str(payload.get("language") or "hinglish").lower()
    if not key or not text:return JSONResponse({"detail":"AI voice is not configured"},status_code=503)
    text=text[:4096] if len(text)>4096 else text; voice=_voice_config().get("male" if gender=="male" else "female")
    if language=="hi":instructions=("Speak as a natural Indian female or male real-estate consultant on a phone call, matching the selected voice. Sound warm, relaxed, attentive and human-conversational, not like a presenter, announcer, audiobook or computer. Use a clearly relaxed medium-slow pace with small pauses between thoughts and after property details. Use subtle pitch and energy changes, gentle emphasis on location, BHK, price and possession, and relaxed sentence endings. Do not rush, do not use a fixed rhythm, and do not sound overly cheerful or salesy. Pronounce Indian names, Mumbai locations and real-estate terms naturally and clearly.")
    elif language=="en":instructions=("Speak as a natural Indian English real-estate consultant on a phone call. Sound warm, relaxed, attentive and human-conversational, not like a presenter, announcer or audiobook. Use a clearly relaxed medium-slow pace with small pauses between thoughts and after property details. Use subtle pitch variation, gentle emphasis on important property details and relaxed sentence endings. Do not rush, use a fixed rhythm, or sound overly salesy. Use natural Indian English pronunciation for Mumbai locations and real-estate terms.")
    else:instructions=("Speak as a natural Indian Hinglish real-estate consultant on a phone call. Sound warm, relaxed, attentive and genuinely conversational, not like a presenter, announcer, audiobook or computer. Use a clearly relaxed medium-slow pace. Pause naturally between thoughts, after commas and around important property details. Vary pitch and energy subtly, emphasize location, BHK, price and possession gently, and finish sentences naturally and softly. Do not rush through property lists. Avoid fixed rhythm, monotone delivery, artificial cheerfulness and exaggerated sales energy. Use natural Indian pronunciation for Mumbai locations, names, numbers and real-estate terms. Keep the delivery comfortable and clear enough for a phone conversation.")
    body={"model":"gpt-4o-mini-tts","voice":voice,"input":text,"instructions":instructions,"speed":0.86,"response_format":"mp3"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:response=await client.post("https://api.openai.com/v1/audio/speech",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=body)
        if response.status_code>=400:return JSONResponse({"detail":"AI voice generation failed"},status_code=502)
        return Response(content=response.content,media_type="audio/mpeg",headers={"Cache-Control":"no-store"})
    except httpx.HTTPError:return JSONResponse({"detail":"AI voice service unavailable"},status_code=502)
@app_main.app.middleware("http")
async def inject_caller_speech_widget(request:Request,call_next):
    response=await call_next(request)
    if request.url.path!="/caller/search" or "text/html" not in response.headers.get("content-type",""):return response
    body=b"".join([chunk async for chunk in response.body_iterator]); marker=b"</body>"; injection=b'<script src="/static/caller-speech.js?v=2"></script>'
    if marker in body and injection not in body:body=body.replace(marker,injection+marker,1)
    headers=dict(response.headers); headers.pop("content-length",None); return Response(content=body,status_code=response.status_code,headers=headers,media_type="text/html")
