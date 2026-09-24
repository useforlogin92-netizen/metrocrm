"""Single persistence engine for the fresh canonical Metro Property Master."""
from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Mapping
from sqlalchemy.orm import Session
from app.models import AuditEvent, Developer, Project, User
from app.property_master import PropertyUpdateSource, normalize_property_payload, validate_property_payload

def _parse_date(value: Any):
    if value in (None, ""): return None
    if isinstance(value, datetime): return value
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try: return datetime.strptime(str(value).strip(), fmt)
        except ValueError: pass
    return None

def apply_property_master(db: Session, *, payload: Mapping[str, Any], source: PropertyUpdateSource | str,
                          actor: User | None = None, project_id: int | None = None,
                          create: bool = False) -> tuple[Project, dict[str, Any]]:
    canonical = normalize_property_payload(payload, source=source)
    errors = validate_property_payload(canonical, is_create=create)
    if errors: raise ValueError("; ".join(errors))
    project = db.get(Project, project_id) if project_id else None
    if project_id and not project: raise ValueError("Property ID not found")
    developer_name = str(canonical.get("developer") or "").strip() or "Unassigned Developer"
    if not project:
        if not create: raise ValueError("Property ID is required for an update")
        developer = db.query(Developer).filter(Developer.name.ilike(developer_name)).first()
        if not developer:
            developer = Developer(name=developer_name); db.add(developer); db.flush()
        project = Project(developer_id=developer.id, name=canonical["project_name"]); db.add(project); db.flush()
    project.name = canonical.get("project_name") or project.name
    for attr, key in (("address","full_address"),("pincode","pincode"),("rera","rera_registration_number")):
        value = canonical.get(key)
        if value is not None: setattr(project, attr, str(value))
    parsed = _parse_date(canonical.get("possession_date"))
    if parsed: project.possession_date = parsed
    if canonical.get("property_type") is not None: project.sector = str(canonical["property_type"])
    existing = {}
    try:
        existing = json.loads(project.description or "{}")
        if not isinstance(existing, dict): existing = {}
    except (TypeError, ValueError): existing = {}
    # Fresh Property Master replaces the old master object instead of merging stale fields.
    old_master = existing.get("property_master")
    master = {k: v for k, v in canonical.items() if not k.startswith("_")}
    master["first_entry_at"] = (old_master or {}).get("first_entry_at") or datetime.utcnow().isoformat()
    master["last_updated_at"] = datetime.utcnow().isoformat()
    master["last_updated_by"] = actor.id if actor else None
    master["update_source"] = canonical["_update_source"]
    existing["property_master"] = master
    project.description = json.dumps(existing, ensure_ascii=False)
    # Project-level amenities are kept in the dedicated model column when available.
    if hasattr(project, "amenities_json") and "facilities" in master:
        project.amenities_json = json.dumps(master.get("facilities") or [], ensure_ascii=False)
    db.add(AuditEvent(actor_user_id=actor.id if actor else None,
        action="PROPERTY_MASTER_UPDATED" if project_id else "PROPERTY_MASTER_CREATED",
        entity_type="Projects", entity_id=str(project.id),
        details=json.dumps({"source": canonical["_update_source"], "fields": sorted(k for k in canonical if not k.startswith("_"))})))
    return project, canonical
