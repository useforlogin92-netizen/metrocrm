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
from app.services.property_pricing import format_property_value, format_rate_per_sqft
router=APIRouter(prefix="/caller/ai-speech",tags=["caller-speech"])
_ALLOWED={"SUPER_ADMIN","ADMIN","MANAGER","TL","SALES_EXECUTIVE","TELECALLER"}
def _user(request:Request,db:Session)->User|None:
    from app.main import _current_user
    return _current_user(request,db)
def _require_user(request:Request,db:Session)->User|None:
    user=_user(request,db); return user if user and user.role in _ALLOWED else None
def _money(value: Any) -> str:
    return format_property_value(value)


def _speech_money(value: Any) -> str:
    """Use natural spoken Indian units in scripts, not terse UI abbreviations."""
    formatted = format_property_value(value)
    if formatted.endswith(" lakh"):
        return formatted[:-5] + " Lakhs"
    if formatted.endswith(" Cr"):
        return formatted[:-3] + " Crores"
    return formatted


def _rate(value: Any) -> str:
    return format_rate_per_sqft(value)
def _human_status(value: Any) -> str:
    """Translate internal status codes into short, caller-friendly wording."""
    raw = str(value or "").strip()
    normalized = raw.upper().replace("-", "_").replace(" ", "_")
    mapping = {
        "READY_TO_MOVE": "ready to move in",
        "READY_TO_MOVE_IN": "ready to move in",
        "UNDER_CONSTRUCTION": "under construction",
        "UNDER_CONSTRUCTION_PROJECT": "under construction",
        "NEW_LAUNCH": "a new launch",
        "NEW_LAUNCH_PROJECT": "a new launch",
        "RESALE": "resale",
    }
    return mapping.get(normalized, raw.replace("_", " ").lower())


def _speech_safe_properties(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allow only caller-useful fields into AI prompts and fallback scripts."""
    safe: list[dict[str, Any]] = []
    excluded = {
        "rera", "rera_number", "rera_registration", "rera_registration_number",
        "price_per_sqft", "rate_per_sqft", "rate", "id", "unit_id", "project_id",
        "score", "reasons", "location_category", "property_type",
    }
    for item in properties[:30]:
        if not isinstance(item, dict):
            continue
        row = {key: value for key, value in item.items() if key not in excluded}
        if row.get("price") is not None:
            row["price"] = _speech_money(row["price"])
        status = row.get("construction_status") or row.get("status") or row.get("availability")
        if status:
            row["construction_status"] = _human_status(status)
        for key in ("status", "availability", "possession_status"):
            row.pop(key, None)
        safe.append(row)
    return safe
def _group_properties(properties:list[dict[str,Any]])->OrderedDict[str,list[dict[str,Any]]]:
    grouped:OrderedDict[str,list[dict[str,Any]]]=OrderedDict()
    for item in properties[:30]:
        if not isinstance(item,dict):continue
        location=str(item.get("locality") or item.get("location") or "Other location").strip(); grouped.setdefault(location,[]).append(item)
    return grouped
def _fallback_script(properties: list[dict[str, Any]], language: str, detail: str) -> str:
    grouped = _group_properties(_speech_safe_properties(properties))
    if not grouped:
        return "Abhi aapki requirement ke liye suitable property option nahi mila. Main details confirm karke aapko update karwa deta hoon."
    if language == "hi":
        opening = "Namaste, aapki requirement ke according maine aapke liye kuch achhe options shortlist kiye hain."
        closing = "Aap bataiye, kab site visit plan karein?"
    elif language == "en":
        opening = "Hello, based on your requirement, I have shortlisted a few suitable options for you."
        closing = "When would you like to plan a site visit?"
    else:
        opening = "Namaste, aapki requirement ke according maine aapke liye best options shortlist kiye hain."
        closing = "Aap bataiye, kab site visit plan karein?"
    lines = [opening]
    for location, items in grouped.items():
        property_lines = []
        for item in items:
            name = str(item.get("project") or item.get("title") or "this project").strip()
            bhk = str(item.get("bhk") or "").strip()
            area = item.get("carpet_area")
            area_text = f"{area:g} square feet carpet area" if isinstance(area, (int, float)) else ""
            status = str(item.get("construction_status") or "").strip()
            price = str(item.get("price") or "").strip()
            description = " ".join(part for part in [
                f"{name} - {bhk}" if bhk else name,
                f"({area_text})" if area_text else "",
                status,
                f"at {price}" if price else "",
            ] if part)
            property_lines.append(description)
        if property_lines:
            lines.append(f"{location} mein: " + "; ".join(property_lines) + ".")
    lines.append(closing)
    return " ".join(lines)


def _openai_key()->str:return os.getenv("OPENAI_API_KEY","").strip()
def _ai_model()->str:return os.getenv("METROCRM_AI_MODEL","gpt-5.6-luna").strip()
def _voice_config()->dict[str,str]:return {"female":os.getenv("METROCRM_TTS_FEMALE_VOICE","coral").strip() or "coral","male":os.getenv("METROCRM_TTS_MALE_VOICE","onyx").strip() or "onyx"}
def _ai_prompt(properties: list[dict[str, Any]], language: str, detail: str) -> str:
    grouped = _group_properties(_speech_safe_properties(properties))
    safe = [{"location": location, "properties": items} for location, items in grouped.items()]
    language_name = {
        "hi": "natural Hindi",
        "en": "professional Indian English",
        "hinglish": "natural Indian Hinglish using English letters",
    }.get(language, "natural Indian Hinglish using English letters")
    return json.dumps({"language": language_name, "detail": detail, "properties_by_location": safe}, ensure_ascii=False)


async def _generate_with_openai(properties:list[dict[str,Any]],language:str,detail:str)->str|None:
    key=_openai_key()
    if not key:return None
    system=("You are a professional Indian real-estate sales agent speaking to a customer on a phone call. Write a ready-to-speak, natural conversational script in the requested language. Start with the idea: Namaste, aapki requirement ke according maine [Location] mein best options shortlist kiye hain. Then describe each option naturally in this order: [Project Name] - [BHK] ([Carpet Area]) [human-friendly construction status] at [Budget in Lakhs/Crores]. End with: Aap bataiye kab site visit plan karein? Adapt naturally for Hindi or professional English when requested. Use only supplied facts and do not invent missing details. Always say prices in clean Indian units, such as 95 Lakhs, 1.3 Crores or 2 Crores; never read raw rupee digits. Completely exclude RERA numbers, per-square-foot rates, internal IDs, ranking scores, database constants and technical labels. Never say internal enum values such as READY_TO_MOVE or APARTMENT. Use status only if human-friendly; otherwise omit it. Mention carpet area in square feet when available. Keep the tone warm, concise, confident and conversational, with natural pauses and no robotic list narration. Do not mention AI, CRM, JSON, prompts or technical details. End by inviting the customer to plan a site visit.")
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
    content_type=response.headers.get("content-type","")
    if "text/html" not in content_type or request.url.path not in {"/caller/search"} and not request.url.path.startswith("/property-submission/"):
        return response
    body=b"".join([chunk async for chunk in response.body_iterator]); marker=b"</body>"
    if request.url.path=="/caller/search":
        injection=b'<script src="/static/caller-speech.js?v=2"></script>'
    else:
        injection=b'<script src="/static/property-pricing.js?v=1"></script>'
    if marker in body and injection not in body:body=body.replace(marker,injection+marker,1)
    headers=dict(response.headers); headers.pop("content-length",None); return Response(content=body,status_code=response.status_code,headers=headers,media_type="text/html")
