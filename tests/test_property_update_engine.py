from app.models import Project, PropertyConfiguration
from app.property_master import PropertyUpdateSource
from app.services.property_update_engine import apply_property_master


def _payload(name="Sample Heights"):
    return {
        "project_name": name,
        "property_type": "Residential",
        "full_address": "Andheri East, Mumbai",
        "city": "Mumbai",
        "locality": "Andheri East",
        "pincode": "400069",
        "developer": "Example Developer",
        "configurations": [
            {
                "configuration": "2 BHK",
                "carpet_area": 700,
                "bundle_rate": 17500000,
            }
        ],
    }


def test_bundle_rate_persists_in_relational_configuration(db_session):
    project, _ = apply_property_master(
        db_session,
        payload=_payload(),
        source=PropertyUpdateSource.INDIVIDUAL,
        create=True,
    )
    db_session.commit()
    row = db_session.query(PropertyConfiguration).filter_by(project_id=project.id).one()
    assert float(row.bundle_rate) == 17500000
    assert float(row.price_including_all) == 17500000
    assert float(row.rate_per_sqft) == 25000


def test_duplicate_create_updates_existing_project(db_session):
    first, _ = apply_property_master(
        db_session,
        payload=_payload(),
        source=PropertyUpdateSource.BULK,
        create=True,
    )
    second, _ = apply_property_master(
        db_session,
        payload={**_payload(), "configurations": []},
        source=PropertyUpdateSource.BULK,
        create=True,
    )
    assert first.id == second.id
    assert db_session.query(Project).count() == 1
