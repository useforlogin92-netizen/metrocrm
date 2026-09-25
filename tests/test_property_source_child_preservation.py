from app.models import PropertyConfiguration, Tower
from app.services.property_update_engine import apply_property_master


def _seed(db):
    project, _ = apply_property_master(
        db,
        payload={
            "Project Name": "Source Preserve Heights",
            "Property Type": "Residential",
            "Full Address": "Mumbai",
            "City": "Mumbai",
            "Locality / Area": "Andheri East",
            "Pincode": "400069",
            "Developer / Builder": "Source Developer",
            "Configuration Details": [
                {"configuration": "2 BHK", "carpet_area": 800, "price_including_all": 16000000}
            ],
            "Tower Details": [{"tower_name": "Tower A", "total_floors": 20}],
        },
        source="BULK",
        create=True,
    )
    db.commit()
    return project


def test_source_partial_update_preserves_children_when_collections_are_omitted(db_session):
    project = _seed(db_session)

    apply_property_master(
        db_session,
        payload={
            "Project Name": "Source Preserve Heights",
            "Property Type": "Residential",
            "City": "Mumbai",
            "Locality / Area": "Powai",
            "Full Address": "Powai, Mumbai",
        },
        source="WHATSAPP",
        project_id=project.id,
        create=False,
    )
    db_session.commit()

    assert db_session.query(PropertyConfiguration).filter_by(project_id=project.id).count() == 1
    assert db_session.query(Tower).filter_by(project_id=project.id).count() == 1


def test_source_explicit_child_collections_replace_existing_children(db_session):
    project = _seed(db_session)

    apply_property_master(
        db_session,
        payload={
            "Project Name": "Source Preserve Heights",
            "Property Type": "Residential",
            "Full Address": "Mumbai",
            "City": "Mumbai",
            "Locality / Area": "Andheri East",
            "Pincode": "400069",
            "Configurations": [
                {"configuration": "3 BHK", "carpet_area": 1200, "rate_per_sqft": 20000}
            ],
            "Tower Details": [{"tower_name": "Tower B", "total_floors": 24}],
        },
        source="SM_LINK",
        project_id=project.id,
        create=False,
    )
    db_session.commit()

    configs = db_session.query(PropertyConfiguration).filter_by(project_id=project.id).all()
    towers = db_session.query(Tower).filter_by(project_id=project.id).all()
    assert [(row.configuration, float(row.carpet_area)) for row in configs] == [("3 BHK", 1200.0)]
    assert [(row.name, row.floors) for row in towers] == [("Tower B", 24)]
