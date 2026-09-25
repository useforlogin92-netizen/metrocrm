import json
from app.routers.property_data import _source_configuration_rows, _source_tower_rows
from app.services.property_update_engine import apply_property_master


def test_source_configuration_preserves_incomplete_values():
    raw = {
        "BHK": "2 BHK",
        "Configuration": "2 BHK",
        "Carpet Area": "860 / 871",
        "Bundle Price": "",
        "Tower/Wing / Structure": "G+37",
        "Possession": "December 2028",
        "Construction Status": "Under Construction",
    }
    rows = _source_configuration_rows(raw, "Available")
    assert len(rows) == 2
    assert [row["carpet_area"] for row in rows] == [860.0, 871.0]
    assert all(row["price_including_all"] is None for row in rows)
    assert rows[0]["_source_details"]["Tower/Wing / Structure"] == "G+37"


def test_bulk_engine_accepts_source_incomplete_configuration(db_session):
    project, _ = apply_property_master(
        db_session,
        payload={
            "Project ID": "MP-TEST-001",
            "Project Name": "Source Incomplete Project",
            "Property Type": "Residential",
            "City": "Mumbai",
            "Locality / Area": "Kandivali East",
            "Full Address": "Source address",
            "Pincode": "400101",
            "configurations": [
                {
                    "configuration": "2 BHK",
                    "carpet_area": None,
                    "price_including_all": None,
                    "rate_per_sqft": None,
                    "_source_details": {"raw": "2 BHK - price not provided"},
                }
            ],
        },
        source="BULK",
        create=True,
    )
    db_session.commit()
    assert project.id is not None
    assert project.description is not None


def test_bulk_source_allows_verified_blank_location_fields_and_preserves_source_tracking(db_session):
    project, _ = apply_property_master(
        db_session,
        payload={
            "Project ID": "MP-SOURCE-001",
            "Project Name": "Source Blank Location Project",
            "Property Type": "Residential",
            "Full Address": "Verified source address",
            "Pincode": None,
            "City": None,
            "Locality / Area": None,
            "configurations": [
                {
                    "configuration": "2 BHK",
                    "carpet_area": 850,
                    "price_including_all": None,
                    "rate_per_sqft": 15000,
                }
            ],
            "Last Updated Date": "2026-09-25",
            "Data Source": "Project Sheet / Residence Data",
        },
        source="BULK",
        create=True,
    )
    db_session.commit()
    stored = json.loads(project.description or "{}")["property_master"]
    assert stored["data_source"] == "Project Sheet / Residence Data"
    assert stored["last_updated_date"] == "2026-09-25"
