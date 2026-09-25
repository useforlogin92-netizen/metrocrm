import json
from datetime import datetime

import pytest

from app.models import AuditEvent, User
from app.property_master import PropertyUpdateSource
from app.services.property_update_engine import apply_property_master


def _payload(project_name="Metro Heights"):
    return {
        "project_name": project_name,
        "developer": "Test Developer",
        "property_type": "Residential",
        "full_address": "Andheri East, Mumbai",
        "city": "Mumbai",
        "locality": "Andheri East",
        "pincode": "400069",
        "project_status": "Under Construction",
        "possession_date": "2027-12-31",
        "configurations": [
            {
                "configuration": "2 BHK",
                "carpet_area": 850,
                "price_including_all": 18000000,
                "negotiation": "Yes",
                "availability": "Available",
            }
        ],
        "tower_details": [
            {"tower_name": "Tower A", "total_floors": 20, "possession_date": "2027-12-31"}
        ],
        "facilities": ["Car Parking", "Gym", "CCTV"],
        "rera_registration_number": "P51800000000",
        "cp_commission_percent": 2,
    }


@pytest.mark.parametrize("source", list(PropertyUpdateSource))
def test_all_four_update_sources_persist_through_same_property_master_engine(db_session, source):
    actor = User(
        username=f"property-{source.value.lower()}",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
        is_approved=True,
    )
    db_session.add(actor)
    db_session.flush()

    project, canonical = apply_property_master(
        db_session,
        payload=_payload(),
        source=source,
        actor=actor,
        create=True,
    )
    db_session.commit()
    db_session.refresh(project)

    master = json.loads(project.description)["property_master"]
    assert canonical["_update_source"] == source.value
    assert master["update_source"] == source.value
    assert project.name == "Metro Heights"
    assert project.city == "Mumbai"
    assert project.locality == "Andheri East"
    assert project.address == "Andheri East, Mumbai"
    assert project.pincode == "400069"
    assert project.rera == "P51800000000"
    assert project.construction_status == "Under Construction"
    assert project.amenities_json == json.dumps(["Car Parking", "Gym", "CCTV"], ensure_ascii=False)
    assert master["configurations"][0]["rate_per_sqft"] == round(18000000 / 850, 2)
    assert master["tower_details"][0]["total_floors"] == 20

    audit = db_session.query(AuditEvent).filter_by(entity_id=str(project.id)).one()
    assert audit.action == "PROPERTY_MASTER_CREATED"
    assert json.loads(audit.details)["source"] == source.value


def test_existing_property_update_replaces_master_without_losing_first_entry_timestamp(db_session):
    actor = User(
        username="property-update-admin",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
        is_approved=True,
    )
    db_session.add(actor)
    db_session.flush()

    project, _ = apply_property_master(
        db_session,
        payload=_payload("Original Heights"),
        source=PropertyUpdateSource.INDIVIDUAL,
        actor=actor,
        create=True,
    )
    db_session.commit()
    db_session.refresh(project)
    first_entry = json.loads(project.description)["property_master"]["first_entry_at"]

    updated = _payload("Updated Heights")
    updated["city"] = "Thane"
    updated["locality"] = "Ghodbunder Road"
    updated["facilities"] = ["Lift"]

    project, _ = apply_property_master(
        db_session,
        payload=updated,
        source=PropertyUpdateSource.BULK,
        actor=actor,
        project_id=project.id,
        create=False,
    )
    db_session.commit()
    db_session.refresh(project)

    master = json.loads(project.description)["property_master"]
    assert master["first_entry_at"] == first_entry
    assert master["last_updated_by"] == actor.id
    assert master["update_source"] == "BULK"
    assert master["project_name"] == "Updated Heights"
    assert master["city"] == "Thane"
    assert master["locality"] == "Ghodbunder Road"
    assert master["facilities"] == ["Lift"]
    assert project.city == "Thane"
    assert project.locality == "Ghodbunder Road"
    assert project.amenities_json == json.dumps(["Lift"], ensure_ascii=False)
    assert db_session.query(AuditEvent).filter_by(
        entity_id=str(project.id), action="PROPERTY_MASTER_UPDATED"
    ).count() == 1
