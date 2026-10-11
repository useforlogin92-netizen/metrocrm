from __future__ import annotations

import json
import os
from urllib.parse import quote_plus
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.csrf import csrf_token, require_csrf_header

router = APIRouter(tags=["open-source-project-search"])
templates = Jinja2Templates(directory="app/templates")
ALLOWED_ROLES = {"SUPER_ADMIN", "ADMIN"}
STATUS_TERMS = {
    "ready_to_move": '"ready to move" OR completed',
    "under_construction": '"under construction" OR ongoing',
    "upcoming": 'upcoming OR "new launch"',
    "completed": 'completed OR "occupancy certificate"',
    "all": '"ready to move" OR "under construction" OR upcoming OR completed',
}


def _actor(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


def _query_terms(payload: dict) -> str:
    city = str(payload.get("city") or "").strip()[:80]
    locality = str(payload.get("locality") or "").strip()[:100]
    side = str(payload.get("side") or "Both").strip()
    status = str(payload.get("status") or "all")
    terms = [city, locality]
    if side in {"East", "West"}:
        terms.append(side)
    terms.extend(["residential real estate project", STATUS_TERMS.get(status, STATUS_TERMS["all"]), "Maharashtra"])
    if payload.get("developer"):
        terms.append(str(payload["developer"]).strip()[:100])
    if payload.get("rera"):
        terms.append(str(payload["rera"]).strip()[:40])
    return " ".join(x for x in terms if x)


class ProjectSearchRequest(BaseModel):
    city: str = Field(default="Mumbai", max_length=80)
    locality: str = Field(min_length=2, max_length=100)
    side: str = Field(default="Both", pattern="^(East|West|Both)$")
    status: str = Field(default="all", pattern="^(ready_to_move|under_construction|upcoming|completed|all)$")
    developer: str | None = Field(default=None, max_length=100)
    rera: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=10, ge=1, le=20)


@router.get("/super-admin/property-data/open-source-search", response_class=HTMLResponse)
@router.get("/admin/property-data/open-source-search", response_class=HTMLResponse)
def open_source_project_search_page(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in ALLOWED_ROLES:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("open_source_project_search.html", {
        "request": request, "role": actor.role, "username": actor.username,
        "avatar": actor.username[:1].upper(), "csrf_token": csrf_token(request),
        "show_user_management": True, "show_integrations": False, "show_alerts": False,
        "show_approvals": True,
    })


@router.post("/super-admin/property-data/open-source-search/api", dependencies=[Depends(require_csrf_header)])
@router.post("/admin/property-data/open-source-search/api", dependencies=[Depends(require_csrf_header)])
def search_open_source_projects(payload: ProjectSearchRequest, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    if not actor or actor.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="admin_access_required")
    query = _query_terms(payload.model_dump())
    encoded = quote_plus(query)
    links = [
        {"name": "Web search", "url": "https://www.google.com/search?q=" + encoded},
        {"name": "Bing search", "url": "https://www.bing.com/search?q=" + encoded},
        {"name": "MahaRERA project search", "url": "https://www.maharera.maharashtra.gov.in/projects-search-result?project_name=" + quote_plus(payload.rera or payload.locality)},
        {"name": "Developer websites", "url": "https://www.google.com/search?q=" + quote_plus(query + " official developer website")},
    ]
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        return {"status": "provider_not_configured", "query": query, "results": [], "links": links,
                "message": "Automated results require BRAVE_SEARCH_API_KEY in the deployment environment. The public-source links are ready; no project data was saved."}
    req = URLRequest(
        "https://api.search.brave.com/res/v1/web/search?q=" + encoded + "&count=" + str(payload.limit) + "&country=IN&search_lang=en",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key, "User-Agent": "MetroCRM-ProjectSearch/1.0"},
    )
    try:
        with urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        web_results = data.get("web", {}).get("results", [])
        results = []
        for item in web_results[:payload.limit]:
            results.append({
                "title": str(item.get("title") or "")[:300],
                "url": str(item.get("url") or "")[:1500],
                "description": str(item.get("description") or "")[:1200],
                "source": str(item.get("meta_url", {}).get("hostname") or "")[:200],
                "age": str(item.get("age") or item.get("page_age") or "")[:100],
                "published": str(item.get("page_age") or "")[:100],
                "review_required": True,
            })
        return {"status": "ok", "query": query, "results": results, "links": links,
                "message": "Search snippets are leads, not verified project facts. Verify the source and RERA details before adding them to Property Master."}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return {"status": "provider_error", "query": query, "results": [], "links": links,
                "message": "Online search provider could not be reached. Use the source links or retry later.",
                "error_type": type(exc).__name__}
