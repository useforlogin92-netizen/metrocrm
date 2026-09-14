"""MetroCRM Marketing Center: admin publishing + public lead landing pages.

Publishing and campaign management are intentionally restricted to ADMIN and
SUPER_ADMIN. Public landing pages expose only the explicitly shared catalog
payload and create normal CRM leads with campaign/UTM attribution.
"""
from __future__ import annotations

import hashlib
import html
import json
import secrets
from collections import Counter
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogShare
from app.csrf import csrf_token, require_csrf
from app.database import get_db
from app.models import AuditEvent, Customer, Lead, User
from app.marketing_models import MarketingCampaign, MarketingLandingVisit, MarketingLeadEvent

router = APIRouter(tags=["marketing"])


def _current_user(request: Request, db: Session) -> User | None:
    from app.main import _current_user as get_current_user
    return get_current_user(request, db)


def _require_admin(request: Request, db: Session) -> User:
    user = _current_user(request, db)
    if not user or user.role not in {"ADMIN", "SUPER_ADMIN"}:
        raise HTTPException(403, "marketing_management_requires_admin")
    return user


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _landing_url(request: Request, token: str, campaign: MarketingCampaign | None = None) -> str:
    base = str(request.base_url).rstrip("/")
    params = {}
    if campaign:
        if campaign.utm_source:
            params["utm_source"] = campaign.utm_source
        if campaign.utm_medium:
            params["utm_medium"] = campaign.utm_medium
        if campaign.utm_campaign:
            params["utm_campaign"] = campaign.utm_campaign
    suffix = f"?{urlencode(params)}" if params else ""
    return f"{base}/m/{token}{suffix}"


def _catalog_payload(db: Session, share_id: int | None) -> dict:
    if not share_id:
        return {}
    share = db.get(CatalogShare, share_id)
    if not share or not share.active:
        return {}
    try:
        payload = json.loads(share.payload_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_active_catalog_share(db: Session, share_id: int | None) -> bool:
    if not share_id:
        return False
    return bool(db.scalar(select(CatalogShare.id).where(CatalogShare.id == share_id, CatalogShare.active.is_(True))))


def _attribution_values(request: Request, campaign: MarketingCampaign) -> dict[str, str | None]:
    params = request.query_params
    return {
        "source": params.get("utm_source") or campaign.utm_source or campaign.channel,
        "medium": params.get("utm_medium") or campaign.utm_medium,
        "campaign": params.get("utm_campaign") or campaign.utm_campaign,
        "content": params.get("utm_content"),
        "term": params.get("utm_term"),
        "click_id": params.get("fbclid") or params.get("gclid"),
    }


@router.get("/marketing", response_class=HTMLResponse)
def marketing_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    if user.role not in {"ADMIN", "SUPER_ADMIN"}:
        return HTMLResponse("Marketing Center is restricted to Admin and Super Admin.", status_code=403)
    campaigns = db.scalars(select(MarketingCampaign).order_by(MarketingCampaign.id.desc())).all()
    shares = db.scalars(select(CatalogShare).where(CatalogShare.active.is_(True)).order_by(CatalogShare.id.desc()).limit(200)).all()
    csrf = csrf_token(request)
    rows = []
    for campaign in campaigns:
        leads = db.scalar(select(func.count(MarketingLeadEvent.id)).where(MarketingLeadEvent.campaign_id == campaign.id)) or 0
        visits = db.scalar(select(func.count(MarketingLandingVisit.id)).where(MarketingLandingVisit.campaign_id == campaign.id)) or 0
        rows.append(f"<tr><td>{_esc(campaign.name)}</td><td>{_esc(campaign.channel)}</td><td>{_esc(campaign.status)}</td><td>{visits}</td><td>{leads}</td><td><a href='{_esc('/m/' + campaign.landing_token)}' target='_blank' rel='noopener'>Open landing</a></td></tr>")
    share_options = "<option value=''>No property catalog</option>" + "".join(f"<option value='{s.id}'>Share #{s.id} · Project {s.project_id or '-'} · Unit {s.unit_id or '-'}</option>" for s in shares)
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM Marketing Center</title>
<style>body{{font-family:Inter,Arial,sans-serif;background:#f4f7fb;color:#0f172a;margin:0;padding:28px}}.wrap{{max-width:1150px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:22px;margin-bottom:18px;box-shadow:0 5px 18px #0f172a0a}}h1{{margin:0 0 6px}}.muted{{color:#64748b;font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}label{{font-size:12px;font-weight:800;display:block;margin-bottom:5px}}input,select{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:9px;box-sizing:border-box}}button{{background:#2563eb;color:#fff;border:0;border-radius:9px;padding:11px 16px;font-weight:800;cursor:pointer;margin-top:14px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:11px;border-bottom:1px solid #e2e8f0;text-align:left}}a{{color:#2563eb;text-decoration:none}}@media(max-width:760px){{body{{padding:14px}}.grid{{grid-template-columns:1fr}}}}</style></head><body><div class='wrap'>
<div class='card'><h1>Marketing Center</h1><div class='muted'>Admin-only publishing. Build a campaign landing page from an approved MetroCRM property share and track leads back to the campaign.</div></div>
<div class='card'><h2>Create campaign</h2><form method='post' action='/marketing/campaigns'><input type='hidden' name='csrf_token' value='{_esc(csrf)}'><div class='grid'>
<div><label>Campaign name</label><input name='name' required placeholder='Mumbai 2BHK Meta Lead Campaign'></div><div><label>Channel</label><select name='channel'><option>WHATSAPP</option><option>FACEBOOK</option><option>INSTAGRAM</option><option>GOOGLE</option><option>YOUTUBE</option><option>LINKEDIN</option><option>SMS</option><option>EMAIL</option><option>OTHER</option></select></div>
<div><label>Landing title</label><input name='landing_title' required placeholder='2BHK Premium Homes in Thane'></div><div><label>Landing subtitle</label><input name='landing_subtitle' placeholder='Get price, floor plan and availability'></div>
<div><label>Approved property catalog share</label><select name='catalog_share_id'>{share_options}</select></div><div><label>UTM source</label><input name='utm_source' placeholder='facebook'></div>
<div><label>UTM medium</label><input name='utm_medium' placeholder='paid_social'></div><div><label>UTM campaign</label><input name='utm_campaign' placeholder='thane_2bhk_sep_2026'></div>
</div><button type='submit'>Create campaign & landing page</button></form></div>
<div class='card'><h2>Campaigns</h2><table><thead><tr><th>Name</th><th>Channel</th><th>Status</th><th>Visits</th><th>Leads</th><th>Landing</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan=6>No campaigns yet.</td></tr>'}</tbody></table></div>
<div class='card'><div class='muted'>Recommended workflow: first create a customer-safe property share in Catalog Sharing, then create the campaign here. The public page never exposes internal CRM notes, staff assignments, customer contact data, or other sensitive fields.</div></div>
</div></body></html>""")


@router.post("/marketing/campaigns")
def create_campaign(
    request: Request,
    name: str = Form(...),
    channel: str = Form("OTHER"),
    landing_title: str = Form(...),
    landing_subtitle: str = Form(""),
    catalog_share_id: str = Form(""),
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    csrf_token_value: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    user = _require_admin(request, db)
    require_csrf(request, csrf_token_value)
    share_id = int(catalog_share_id) if catalog_share_id.isdigit() else None
    if share_id and not _has_active_catalog_share(db, share_id):
        raise HTTPException(400, "invalid_catalog_share")
    campaign = MarketingCampaign(
        name=name.strip()[:200], channel=channel.strip().upper()[:40] or "OTHER", landing_token=secrets.token_urlsafe(24),
        landing_title=landing_title.strip()[:250], landing_subtitle=landing_subtitle.strip()[:500] or None,
        catalog_share_id=share_id, utm_source=utm_source.strip()[:100] or None, utm_medium=utm_medium.strip()[:100] or None,
        utm_campaign=utm_campaign.strip()[:150] or None, created_by_id=user.id, status="DRAFT",
    )
    db.add(campaign); db.flush()
    db.add(AuditEvent(actor_user_id=user.id, action="MARKETING_CAMPAIGN_CREATED", entity_type="MarketingCampaign", entity_id=str(campaign.id), details=json.dumps({"channel": campaign.channel, "catalog_share_id": share_id})))
    db.commit()
    return RedirectResponse("/marketing", status_code=303)


@router.post("/marketing/campaigns/{campaign_id}/activate")
def activate_campaign(campaign_id: int, request: Request, csrf_token_value: str = Form("", alias="csrf_token"), db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    require_csrf(request, csrf_token_value)
    campaign = db.get(MarketingCampaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "campaign_not_found")
    if not _has_active_catalog_share(db, campaign.catalog_share_id):
        raise HTTPException(400, "active_catalog_share_required")
    campaign.status = "ACTIVE"
    db.add(AuditEvent(actor_user_id=user.id, action="MARKETING_CAMPAIGN_ACTIVATED", entity_type="MarketingCampaign", entity_id=str(campaign.id), details="{}"))
    db.commit()
    return RedirectResponse("/marketing", status_code=303)


@router.get("/marketing/campaigns/{campaign_id}/stats")
def campaign_stats(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    campaign = db.get(MarketingCampaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "campaign_not_found")
    visits = db.scalar(select(func.count(MarketingLandingVisit.id)).where(MarketingLandingVisit.campaign_id == campaign_id)) or 0
    leads = db.scalar(select(func.count(MarketingLeadEvent.id)).where(MarketingLeadEvent.campaign_id == campaign_id)) or 0
    sources = Counter(row.source for row in db.execute(select(MarketingLeadEvent).where(MarketingLeadEvent.campaign_id == campaign_id)).scalars())
    return {"campaign_id": campaign.id, "status": campaign.status, "visits": visits, "leads": leads, "conversion_rate": round((leads / visits * 100), 2) if visits else 0, "lead_sources": dict(sources), "landing_url": _landing_url(request, campaign.landing_token, campaign)}


def _visitor_hash(request: Request) -> str:
    client = request.client.host if request.client else "unknown"
    return hashlib.sha256((client + "|" + (request.headers.get("user-agent") or "")).encode()).hexdigest()


@router.get("/m/{token}", response_class=HTMLResponse)
def public_marketing_landing(token: str, request: Request, db: Session = Depends(get_db)):
    campaign = db.scalar(select(MarketingCampaign).where(MarketingCampaign.landing_token == token, MarketingCampaign.status == "ACTIVE"))
    if not campaign:
        raise HTTPException(404, "campaign_not_found_or_not_active")
    payload = _catalog_payload(db, campaign.catalog_share_id)
    visitor = MarketingLandingVisit(campaign_id=campaign.id, visitor_hash=_visitor_hash(request), referrer=(request.headers.get("referer") or "")[:1000], user_agent=(request.headers.get("user-agent") or "")[:500])
    db.add(visitor); db.commit()
    property_title = payload.get("title") or payload.get("name") or campaign.landing_title or "Property Details"
    description = payload.get("description") or campaign.landing_subtitle or "Get property details and availability from our team."
    photos = payload.get("media") or payload.get("photos") or []
    first_photo = ""
    if isinstance(photos, list) and photos and isinstance(photos[0], dict):
        first_photo = photos[0].get("url") or ""
    fields = []
    for key in ("location", "city", "locality", "bhk", "property_type", "carpet_area", "price", "possession", "amenities"):
        value = payload.get(key)
        if isinstance(value, list): value = ", ".join(str(x) for x in value)
        if value not in (None, "", []): fields.append(f"<div><b>{_esc(key.replace('_',' ').title())}</b><br>{_esc(value)}</div>")
    image = f"<img src='{_esc(first_photo)}' alt='Property' style='width:100%;max-height:360px;object-fit:cover;border-radius:14px;margin-bottom:16px'>" if first_photo else ""
    attribution = _attribution_values(request, campaign)
    hidden_attribution = "".join(f"<input type='hidden' name='{key}' value='{_esc(value)}'>" for key, value in (("utm_source", attribution["source"]), ("utm_medium", attribution["medium"]), ("utm_campaign", attribution["campaign"]), ("utm_content", attribution["content"]), ("utm_term", attribution["term"]), ("fbclid", request.query_params.get("fbclid")), ("gclid", request.query_params.get("gclid"))) if value)
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='description' content='{_esc(description[:155])}'><title>{_esc(campaign.landing_title or property_title)}</title>
<style>body{{font-family:Inter,Arial,sans-serif;background:#f8fafc;color:#0f172a;margin:0}}.wrap{{max-width:900px;margin:auto;padding:22px}}.hero,.form{{background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:22px;box-shadow:0 8px 28px #0f172a0d;margin-bottom:18px}}h1{{font-size:30px;margin:0 0 8px}}p{{color:#475569;line-height:1.6}}.details{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:18px 0}}.details div{{padding:12px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc}}input{{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:10px;margin:6px 0 12px;box-sizing:border-box}}button{{width:100%;padding:13px;border:0;border-radius:10px;background:#2563eb;color:white;font-weight:800;font-size:15px}}@media(max-width:650px){{.details{{grid-template-columns:1fr}}h1{{font-size:24px}}}}</style></head><body><div class='wrap'><div class='hero'>{image}<h1>{_esc(campaign.landing_title or property_title)}</h1><p>{_esc(description)}</p><div class='details'>{''.join(fields)}</div></div><div class='form'><h2>Get details / callback</h2><form method='post' action='/m/{_esc(token)}/lead'><input name='name' placeholder='Your name' required maxlength='200'><input name='mobile' placeholder='Mobile number' required maxlength='30'><input name='email' type='email' placeholder='Email (optional)' maxlength='255'><input name='message' placeholder='What would you like to know?' maxlength='500'>{hidden_attribution}<input type='text' name='website' tabindex='-1' autocomplete='off' style='display:none'><button type='submit'>Request Details</button></form><p style='font-size:12px'>By submitting, you are requesting a callback/details from the business. Your information is used for this enquiry.</p></div></div></body></html>""")


@router.post("/m/{token}/lead")
def public_marketing_lead(
    token: str,
    request: Request,
    name: str = Form(...),
    mobile: str = Form(...),
    email: str = Form(""),
    message: str = Form(""),
    website: str = Form(""),
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    utm_content: str = Form(""),
    utm_term: str = Form(""),
    fbclid: str = Form(""),
    gclid: str = Form(""),
    db: Session = Depends(get_db),
):
    campaign = db.scalar(select(MarketingCampaign).where(MarketingCampaign.landing_token == token, MarketingCampaign.status == "ACTIVE"))
    if not campaign:
        raise HTTPException(404, "campaign_not_found_or_not_active")
    if website.strip():
        return RedirectResponse(f"/m/{token}", status_code=303)
    name = name.strip()[:200]
    mobile = mobile.strip()[:30]
    email = email.strip().lower()[:255] or None
    message = message.strip()[:500] or None
    if not name or len(mobile) < 6:
        raise HTTPException(400, "valid_name_and_mobile_required")
    customer = Customer(name=name, mobile=mobile, email=email, notes=message)
    db.add(customer); db.flush()
    lead = Lead(customer_id=customer.id, source=f"MARKETING_{campaign.channel}", status="NEW", requirement=message)
    db.add(lead); db.flush()
    query_values = _attribution_values(request, campaign)
    event = MarketingLeadEvent(
        campaign_id=campaign.id,
        lead_id=lead.id,
        source=(utm_source.strip()[:100] or query_values["source"]),
        medium=(utm_medium.strip()[:100] or query_values["medium"]),
        campaign=(utm_campaign.strip()[:150] or query_values["campaign"]),
        content=(utm_content.strip()[:200] or query_values["content"]),
        term=(utm_term.strip()[:200] or query_values["term"]),
        click_id=(fbclid.strip()[:255] or gclid.strip()[:255] or query_values["click_id"]),
        landing_path=str(request.url.path),
    )
    db.add(event)
    db.add(AuditEvent(action="MARKETING_LEAD_CAPTURED", entity_type="Lead", entity_id=str(lead.id), details=json.dumps({"campaign_id": campaign.id, "channel": campaign.channel})))
    db.commit()
    return RedirectResponse(f"/m/{token}?submitted=1", status_code=303)
