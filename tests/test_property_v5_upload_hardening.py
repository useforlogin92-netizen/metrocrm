import json
from decimal import Decimal

from app.models import Developer, NearbyLocation, Project, PropertyConfiguration, Tower, Unit
from app.metro_property_v5 import HEADERS, build_v5_workbook, import_v5_workbook


MODELS = (Developer, Project, PropertyConfiguration, Tower, Unit, NearbyLocation)


def _quick_import_workbook(rows):
    workbook = build_v5_workbook()
    sheet = workbook["QuickImport"]
    for row in rows:
        sheet.append([row.get(header) for header in HEADERS["QuickImport"]])
    return workbook


def _row(project="Sample Heights", tower="Tower A", unit="101", price=10_000_000, **extra):
    return {
        "Developer / Builder": "Sample Developer",
        "Project Name": project,
        "City": "Mumbai",
        "State": "Maharashtra",
        "Locality / Area": "Malad East",
        "BHK / Configuration": "2 BHK",
        "Carpet Area (sq.ft.)": 650,
        "Rate / sq.ft.": 15000,
        "Bundle / Total Price": price,
        "Tower / Wing": tower,
        "Unit / Flat No.": unit,
        "Availability": "Available",
        "Nearby Station": "Malad",
        "Station Distance": "1 km",
        **extra,
    }


def test_quick_import_is_idempotent_and_updates_existing_values(db_session):
    workbook = _quick_import_workbook([_row()])
    import_v5_workbook(db_session, MODELS, workbook, actor=None)
    db_session.commit()

    updated_workbook = _quick_import_workbook([_row(price=11_000_000)])
    import_v5_workbook(db_session, MODELS, updated_workbook, actor=None)
    db_session.commit()

    assert db_session.query(Developer).count() == 1
    assert db_session.query(Project).count() == 1
    assert db_session.query(PropertyConfiguration).count() == 1
    assert db_session.query(Tower).count() == 1
    assert db_session.query(Unit).count() == 1
    assert db_session.query(NearbyLocation).count() == 1
    project = db_session.query(Project).one()
    assert project.city == "Mumbai"
    assert project.state == "Maharashtra"
    assert json.loads(project.description)["quick_import_rows"]
    unit = db_session.query(Unit).one()
    assert unit.price == Decimal("11000000.00")


def test_quick_import_does_not_merge_same_unit_number_across_towers(db_session):
    workbook = _quick_import_workbook([
        _row(tower="Tower A", unit="101"),
        _row(tower="Tower B", unit="101"),
    ])
    import_v5_workbook(db_session, MODELS, workbook, actor=None)
    db_session.commit()

    units = db_session.query(Unit).order_by(Unit.id).all()
    assert len(units) == 2
    assert units[0].unit_number == units[1].unit_number == "101"
    assert units[0].tower_id != units[1].tower_id
    assert db_session.query(Tower).count() == 2


def test_quick_import_skips_ambiguous_unit_update_without_tower(db_session):
    workbook = _quick_import_workbook([
        _row(tower="Tower A", unit="101", price=10_000_000),
        _row(tower="Tower B", unit="101", price=12_000_000),
        _row(tower="", unit="101", price=13_000_000),
    ])
    _, _, warnings = import_v5_workbook(db_session, MODELS, workbook, actor=None)
    db_session.commit()

    assert len(db_session.query(Unit).all()) == 2
    assert any("ambiguous across towers" in warning for warning in warnings)
    assert {str(unit.price) for unit in db_session.query(Unit).all()} == {"10000000.00", "12000000.00"}


def test_structured_units_match_by_project_unit_and_tower(db_session):
    developer = Developer(name="Existing Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Existing Heights")
    db_session.add(project)
    db_session.flush()
    tower_a = Tower(project_id=project.id, name="Tower A")
    tower_b = Tower(project_id=project.id, name="Tower B")
    db_session.add_all([tower_a, tower_b])
    db_session.flush()

    workbook = build_v5_workbook()
    sheet = workbook["Units"]
    headers = HEADERS["Units"]
    for tower in (tower_a, tower_b):
        row = {"project_id": project.id, "tower_id": tower.id, "unit_number": "101", "bhk": "2 BHK"}
        sheet.append([row.get(header) for header in headers])

    import_v5_workbook(db_session, MODELS, workbook, actor=None)
    db_session.commit()

    units = db_session.query(Unit).filter(Unit.project_id == project.id).all()
    assert len(units) == 2
    assert {unit.tower_id for unit in units} == {tower_a.id, tower_b.id}
