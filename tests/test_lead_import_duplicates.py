from io import BytesIO

from openpyxl import Workbook

from app.models import Customer, Lead, User
from app.routers.lead_import import LEAD_FIELDS, _import_leads


def _actor(db_session):
    actor = User(username="duplicate-import-admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add(actor)
    db_session.commit()
    return actor


def _workbook(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Leads"
    sheet.append(LEAD_FIELDS)
    for row in rows:
        sheet.append([row.get(field) for field in LEAD_FIELDS])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _row(sr_no=1, **overrides):
    row = {
        "sr_no": sr_no, "customer_name": "Asha Mehta", "mobile": "9876501234",
        "email": "asha@example.com", "source": "Website", "status": "NEW",
        "requirement": "2 BHK near Borivali", "budget_min": 5000000,
        "budget_max": 8000000, "preferred_location": "Borivali",
        "bhk": "2 BHK", "property_type": "Apartment", "buy_rent": "BUY",
    }
    row.update(overrides)
    return row


def test_duplicate_leads_inside_one_workbook_roll_back_everything(db_session):
    actor = _actor(db_session)
    content = _workbook([_row(1), _row(2)])

    created, updated, errors = _import_leads(content, actor, db_session)

    assert created == 0
    assert updated == 0
    assert any("duplicate lead row" in error for error in errors)
    assert db_session.query(Lead).count() == 0
    assert db_session.query(Customer).count() == 0


def test_duplicate_of_existing_active_lead_is_rejected(db_session):
    actor = _actor(db_session)
    customer = Customer(name="Asha Mehta", mobile="9876501234", email="asha@example.com")
    db_session.add(customer)
    db_session.flush()
    existing = Lead(
        customer_id=customer.id, source="Website", status="CONTACTED",
        requirement="2 BHK near Borivali", budget_min=5000000, budget_max=8000000,
        preferred_location="Borivali", bhk="2 BHK", property_type="Apartment", buy_rent="BUY",
    )
    db_session.add(existing)
    db_session.commit()

    created, updated, errors = _import_leads(_workbook([_row()]), actor, db_session)

    assert created == 0
    assert updated == 0
    assert any(f"lead_id {existing.id}" in error for error in errors)
    assert db_session.query(Lead).count() == 1


def test_explicit_lead_id_updates_existing_record_instead_of_duplicate_rejection(db_session):
    actor = _actor(db_session)
    customer = Customer(name="Asha Mehta", mobile="9876501234", email="asha@example.com")
    db_session.add(customer)
    db_session.flush()
    existing = Lead(
        customer_id=customer.id, source="Website", status="CONTACTED",
        requirement="2 BHK near Borivali", budget_min=5000000, budget_max=8000000,
        preferred_location="Borivali", bhk="2 BHK", property_type="Apartment", buy_rent="BUY",
    )
    db_session.add(existing)
    db_session.commit()

    created, updated, errors = _import_leads(_workbook([_row(1, lead_id=existing.id, status="QUALIFIED")]), actor, db_session)

    assert (created, updated, errors) == (0, 1, [])
    db_session.refresh(existing)
    assert existing.status == "QUALIFIED"
    assert db_session.query(Lead).count() == 1
