"""Single persistence engine for the fresh canonical Metro Property Master."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from sqlalchemy.orm import Session
from app.models import AuditEvent, Developer, Project, PropertyConfiguration, Tower, User
from app.property_master import PropertyUpdateSource, normalize_property_payload, validate_property_payload

def _parse_date(value: Any):
    if value in (None, ""): return None
    if isinstance(value, datetime): return value
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try: return datetime.strptime(str(value).strip(), fmt)
        except ValueError: pass
    return None


def _sync_project_children(db: Session, project: Project, canonical: Mapping[str, Any]) -> None:
    """Persist project configurations/towers as relational children.

    Child collections are authoritative only when the source payload includes the
    corresponding key, so partial individual updates do not erase existing data.
    """
    if "configurations" in canonical:
        db.query(PropertyConfiguration).filter(PropertyConfiguration.project_id == project.id).delete(
            synchronize_session=False
        )
        for index, row in enumerate(canonical.get("configurations") or []):
            db.add(PropertyConfiguration(
                project_id=project.id,
                configuration=str(row.get("configuration") or "").strip(),
                carpet_area=Decimal(str(row["carpet_area"])) if row.get("carpet_area") is not None else None,
                price_including_all=Decimal(str(row["price_including_all"])) if row.get("price_including_all") is not None else None,
                rate_per_sqft=Decimal(str(row["rate_per_sqft"])) if row.get("rate_per_sqft") is not None else None,
                negotiation=str(row.get("negotiation") or "").strip().upper() or None,
                availability=str(row.get("availability") or "").strip() or None,
                sort_order=index,
                source_details=json.dumps(row.get("_source_details") or {}, ensure_ascii=False) if row.get("_source_details") else None,
            ))
    if "tower_details" in canonical:
        db.query(Tower).filter(Tower.project_id == project.id).delete(synchronize_session=False)
        for row in canonical.get("tower_details") or []:
            possession = _parse_date(row.get("possession_date"))
            db.add(Tower(
                project_id=project.id,
                name=str(row.get("tower_name") or "").strip(),
                floors=int(row["total_floors"]) if row.get("total_floors") not in (None, "") else None,
                possession_date=possession,
                details=json.dumps({k: v for k, v in row.items() if k not in {"tower_name", "total_floors", "possession_date"}}, ensure_ascii=False),
            ))

def apply_property_master(db: Session, *, payload: Mapping[str, Any], source: PropertyUpdateSource | str,
                          actor: User | None = None, project_id: int | None = None,
                          create: bool = False) -> tuple[Project, dict[str, Any]]:
    canonical = normalize_property_payload(payload, source=source)
    if canonical.get("_update_source") == PropertyUpdateSource.BULK.value:
        canonical["_allow_incomplete_master"] = True

    errors = validate_property_payload(
        canonical,
        is_create=create,
        allow_incomplete_configurations=canonical.get("_update_source") == PropertyUpdateSource.BULK.value,
    )
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
    for attr, key in (
        ("address", "full_address"),
        ("city", "city"),
        ("locality", "locality"),
        ("pincode", "pincode"),
        ("rera", "rera_registration_number"),
        ("construction_status", "project_status"),
    ):
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
    now_iso = datetime.now(timezone.utc).isoformat()
    master["first_entry_at"] = (old_master or {}).get("first_entry_at") or now_iso
    master["last_updated_at"] = now_iso
    master["last_updated_by"] = actor.id if actor else None
    master["update_source"] = canonical["_update_source"]
    if canonical.get("last_updated_date") is not None:
        master["last_updated_date"] = canonical["last_updated_date"]
    if canonical.get("data_source") is not None:
        master["data_source"] = canonical["data_source"]
    existing["property_master"] = master
    _sync_project_children(db, project, canonical)
    project.description = json.dumps(existing, ensure_ascii=False)
    # Project-level amenities are kept in the dedicated model column when available.
    if hasattr(project, "amenities_json") and "facilities" in master:
        project.amenities_json = json.dumps(master.get("facilities") or [], ensure_ascii=False)
    db.add(AuditEvent(actor_user_id=actor.id if actor else None,
        action="PROPERTY_MASTER_UPDATED" if project_id else "PROPERTY_MASTER_CREATED",
        entity_type="Projects", entity_id=str(project.id),
        details=json.dumps({"source": canonical["_update_source"], "fields": sorted(k for k in canonical if not k.startswith("_"))})))
    return project, canonical
