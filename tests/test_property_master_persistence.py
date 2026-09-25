from app.models import Developer, Project, PropertyConfiguration, Tower
from app.services.property_update_engine import apply_property_master


def _payload():
    return {
        "Property Ref": "P-001",
        "Developer / Builder": "Example Developer",
        "Project Name": "Sample Heights",
        "Property Type": "Residential",
        "Full Address": "Andheri East, Mumbai",
        "City": "Mumbai",
        "Locality / Area": "Andheri East",
        "Pincode": "400069",
        "Configuration Details": [
            {"configuration": "2 BHK", "carpet_area": 850, "price_including_all": 18000000, "negotiation": "Yes", "availability": "Available"},
            {"configuration": "3 BHK", "carpet_area": 1200, "rate_per_sqft": 18000, "negotiation": "No", "availability": "Available"},
        ],
        "Tower Details": [
            {"tower_name": "Tower A", "total_floors": 22},
            {"tower_name": "Tower B", "total_floors": 24},
        ],
    }


def test_property_master_persists_project_children(db_session):
    project, canonical = apply_property_master(
        db_session, payload=_payload(), source="BULK", create=True
    )
    db_session.commit()

    assert canonical["configurations"][0]["rate_per_sqft"] == round(18000000 / 850, 2)
    configurations = db_session.query(PropertyConfiguration).filter_by(project_id=project.id).order_by(PropertyConfiguration.sort_order).all()
    towers = db_session.query(Tower).filter_by(project_id=project.id).order_by(Tower.id).all()

    assert [(row.configuration, float(row.carpet_area), float(row.price_including_all)) for row in configurations] == [
        ("2 BHK", 850.0, 18000000.0),
        ("3 BHK", 1200.0, 21600000.0),
    ]
    assert [(row.name, row.floors) for row in towers] == [("Tower A", 22), ("Tower B", 24)]


def test_partial_project_update_preserves_existing_children(db_session):
    project, _ = apply_property_master(
        db_session, payload=_payload(), source="BULK", create=True
    )
    db_session.commit()

    apply_property_master(
        db_session,
        payload={"City": "Mumbai", "Locality / Area": "Powai"},
        source="INDIVIDUAL",
        project_id=project.id,
        create=False,
    )
    db_session.commit()

    assert db_session.query(PropertyConfiguration).filter_by(project_id=project.id).count() == 2
    assert db_session.query(Tower).filter_by(project_id=project.id).count() == 2
    assert db_session.get(Project, project.id).locality == "Powai"


def test_project_model_is_registered_with_new_configuration_table(db_session):
    developer = Developer(name="Example Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Example")
    db_session.add(project)
    db_session.commit()

    row = PropertyConfiguration(
        project_id=project.id,
        configuration="1 BHK",
        carpet_area=500,
        price_including_all=9000000,
        rate_per_sqft=18000,
        negotiation="NO",
        availability="Available",
    )
    db_session.add(row)
    db_session.commit()

    assert row.id is not None
