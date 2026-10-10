from types import SimpleNamespace

from app.routers.caller_assistant import _lead_in_scope, _lead_locations, _opening_speeches, _property_speeches


class FakeDB:
    def __init__(self, users):
        self.users = users

    def scalars(self, stmt):
        class Result:
            def __init__(self, users):
                self._users = users

            def all(self):
                # Mirror the reporting_manager_id == current-scope-id filter used by
                # _lead_in_scope without depending on SQLAlchemy execution in unit tests.
                try:
                    values = stmt.compile().params.values()
                    ids = set()
                    for value in values:
                        if isinstance(value, (list, tuple, set, frozenset)):
                            ids.update(value)
                        elif value is not None:
                            ids.add(value)
                except Exception:
                    ids = set()
                return [u for u in self._users if getattr(u, "reporting_manager_id", None) in ids]

        return Result(self.users)


def test_multiple_locations_preserve_side_and_priority():
    lead = SimpleNamespace(preferred_location="Borivali, Andheri")
    requirement = SimpleNamespace(locations_json='[{"name":"Borivali","side":"Both","priority":"Primary"},{"name":"Andheri","side":"West","priority":"Secondary"}]')
    assert _lead_locations(lead, requirement) == [
        {"name":"Borivali","side":"Both","priority":"Primary"},
        {"name":"Andheri","side":"West","priority":"Secondary"},
    ]


def test_opening_speech_uses_source_and_caller_name():
    user = SimpleNamespace(username="Suresh")
    lead = SimpleNamespace(source="MagicBricks", preferred_location="Borivali, Andheri", bhk="2 BHK")
    customer = SimpleNamespace(name="Rahul")
    speeches = _opening_speeches(user, lead, customer, [{"name":"Borivali","side":"Both","priority":"Primary"},{"name":"Andheri","side":"Both","priority":"Primary"}])
    text = speeches["en"]
    assert "Suresh" in text
    assert "MagicBricks" in text
    assert "Rahul" in text
    assert "Borivali, Andheri" in text
    assert "2 BHK" in text


def test_property_speech_contains_sales_details():
    customer = SimpleNamespace(name="Rahul")
    property_data = {
        "project":"ABC Residency", "location":"Borivali West", "bhk":"2 BHK",
        "carpet_area":650.0, "price_per_sqft":12000.0, "price":7800000.0,
        "parking":"2", "negotiable":"Yes", "possession":"Dec 2027", "rera":"P123",
        "description":"Near station",
    }
    speeches = _property_speeches(property_data, customer)
    text = speeches["en"]
    for expected in ("ABC Residency","Borivali West","2 BHK","650","12,000","7,800,000","2","negotiable","Dec 2027","P123"):
        assert expected in text


def test_caller_scope_allows_assigned_lead():
    user = SimpleNamespace(id=10, role="SALES_EXECUTIVE")
    lead = SimpleNamespace(assigned_user_id=10)
    assert _lead_in_scope(user, lead, FakeDB([])) is True


def test_caller_scope_denies_other_sales_lead():
    user = SimpleNamespace(id=10, role="SALES_EXECUTIVE")
    lead = SimpleNamespace(assigned_user_id=11)
    assert _lead_in_scope(user, lead, FakeDB([])) is False


def test_caller_scope_allows_manager_reporting_tree():
    manager = SimpleNamespace(id=10, role="MANAGER")
    child = SimpleNamespace(id=11, reporting_manager_id=10)
    grandchild = SimpleNamespace(id=12, reporting_manager_id=11)
    lead = SimpleNamespace(assigned_user_id=12)
    assert _lead_in_scope(manager, lead, FakeDB([child, grandchild])) is True


def test_caller_scope_denies_manager_outside_tree():
    manager = SimpleNamespace(id=10, role="MANAGER")
    child = SimpleNamespace(id=11, reporting_manager_id=10)
    outsider = SimpleNamespace(id=20, reporting_manager_id=99)
    lead = SimpleNamespace(assigned_user_id=20)
    assert _lead_in_scope(manager, lead, FakeDB([child, outsider])) is False


def test_admin_scope_can_open_any_lead():
    admin = SimpleNamespace(id=1, role="ADMIN")
    lead = SimpleNamespace(assigned_user_id=999)
    assert _lead_in_scope(admin, lead, FakeDB([])) is True

# CI regression coverage for caller lead isolation.



def _post_request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "POST", "path": "/test", "headers": [], "query_string": b""})


def test_optional_amount_parser_validates_budget_values():
    from decimal import Decimal
    import pytest
    from app.routers.caller_assistant import _parse_optional_amount

    assert _parse_optional_amount("5000000", "Minimum budget") == Decimal("5000000")
    assert _parse_optional_amount("", "Minimum budget") is None
    with pytest.raises(ValueError):
        _parse_optional_amount("-1", "Minimum budget")
    with pytest.raises(ValueError):
        _parse_optional_amount("not-a-number", "Minimum budget")


def test_sales_executive_can_update_customer_and_requirement_for_assigned_lead(db_session, monkeypatch):
    from app.models import Customer, CustomerRequirement, Lead, User
    from app.routers import caller_assistant

    actor = User(username="sales-workbench", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Old Customer", mobile="9876500000")
    db_session.add_all([actor, customer])
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="NEW", assigned_user_id=actor.id)
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(caller_assistant, "_current_user", lambda request, db: actor)
    monkeypatch.setattr(caller_assistant, "require_csrf", lambda request, token: None)

    response = caller_assistant.update_lead_requirements(
        lead_id=lead.id, request=_post_request(), customer_name="Updated Customer",
        mobile="9876512345", alternate_mobile="9123456780", email="CUSTOMER@example.com",
        customer_notes="Prefers evening calls", requirement_text="Ready possession near station",
        budget_min="5000000", budget_max="8500000", preferred_locations="Borivali, Kandivali",
        bhk="2 BHK", property_type="Apartment", buy_rent="BUY",
        property_category="", carpet_area_min="", carpet_area_max="", possession_requirement="",
        furnishing="", parking="", project_preference="", developer_preference="", loan_required=False, purpose="",
        requirement_notes="Loan required", csrf_token_value="test", db=db_session,
    )

    assert response.status_code == 303
    db_session.refresh(customer)
    db_session.refresh(lead)
    requirement = db_session.query(CustomerRequirement).filter_by(customer_id=customer.id, is_active=True).one()
    assert customer.name == "Updated Customer"
    assert customer.mobile == "9876512345"
    assert customer.email == "customer@example.com"
    assert lead.budget_min == 5000000
    assert lead.budget_max == 8500000
    assert lead.preferred_location == "Borivali, Kandivali"
    assert requirement.bhk == "2 BHK"
    assert requirement.buy_rent == "BUY"
    assert "Borivali" in requirement.locations_json


def test_sales_executive_can_schedule_followup_for_assigned_lead(db_session, monkeypatch):
    from app.models import Customer, FollowUp, Lead, User
    from app.routers import caller_assistant

    actor = User(username="sales-followup", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Follow-up Customer", mobile="9876501111")
    db_session.add_all([actor, customer])
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="REFERRAL", status="CONTACTED", assigned_user_id=actor.id)
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(caller_assistant, "_current_user", lambda request, db: actor)
    monkeypatch.setattr(caller_assistant, "require_csrf", lambda request, token: None)

    response = caller_assistant.schedule_lead_followup(
        lead_id=lead.id, request=_post_request(), due_at="2026-10-12T10:00",
        purpose="Call follow-up", notes="Confirm site visit interest",
        csrf_token_value="test", db=db_session,
    )

    followup = db_session.query(FollowUp).filter_by(lead_id=lead.id).one()
    assert response.status_code == 303
    assert followup.assigned_user_id == actor.id
    assert followup.completed is False
    assert followup.purpose == "Call follow-up"



def test_matched_property_rows_include_project_id_for_whatsapp_share(db_session):
    from app.models import Developer, Project, Unit
    from app.routers.caller_assistant import _property_rows

    developer = Developer(name="Test Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Test Residency", city="Mumbai", locality="Borivali")
    db_session.add(project)
    db_session.flush()
    unit = Unit(project_id=project.id, unit_number="A-101", bhk="2 BHK", property_type="Apartment", price=8000000)
    db_session.add(unit)
    db_session.commit()

    properties = _property_rows(db_session, {"city": "Mumbai", "preferred_locations": [], "construction_statuses": []})

    match = next(item for item in properties if item["id"] == unit.id)
    assert match["project_id"] == project.id



def test_customer_matching_excludes_sold_units_even_when_project_is_ready_to_move(db_session):
    from app.models import Developer, Project, Unit
    from app.routers.caller_assistant import _property_rows

    developer = Developer(name="Inventory Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Inventory Residency", city="Mumbai", locality="Kandivali", construction_status="READY_TO_MOVE")
    db_session.add(project)
    db_session.flush()
    sold = Unit(project_id=project.id, unit_number="A-101", bhk="2 BHK", property_type="Apartment", price=8000000, status="SOLD")
    available = Unit(project_id=project.id, unit_number="A-102", bhk="2 BHK", property_type="Apartment", price=8200000, status="AVAILABLE")
    db_session.add_all([sold, available])
    db_session.commit()

    properties = _property_rows(db_session, {"city": "Mumbai", "preferred_locations": ["Kandivali"], "construction_statuses": []})

    ids = {item["id"] for item in properties}
    assert sold.id not in ids
    assert available.id in ids


def test_customer_matching_excludes_sold_out_project_inventory(db_session):
    from app.models import Developer, Project, Unit
    from app.routers.caller_assistant import _property_rows

    developer = Developer(name="Sold Out Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Sold Out Residency", city="Mumbai", locality="Borivali", construction_status="SOLD_OUT")
    db_session.add(project)
    db_session.flush()
    unit = Unit(project_id=project.id, unit_number="B-201", bhk="2 BHK", property_type="Apartment", price=9000000, status="AVAILABLE")
    db_session.add(unit)
    db_session.commit()

    properties = _property_rows(db_session, {"city": "Mumbai", "preferred_locations": ["Borivali"], "construction_statuses": []})

    assert unit.id not in {item["id"] for item in properties}



def test_sales_executive_can_save_full_real_estate_qualification(db_session, monkeypatch):
    from app.models import Customer, CustomerRequirement, Lead, User
    from app.routers import caller_assistant

    actor = User(username="sales-full-qualification", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Qualification Customer", mobile="9876509876")
    db_session.add_all([actor, customer])
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="QUALIFIED", assigned_user_id=actor.id)
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(caller_assistant, "_current_user", lambda request, db: actor)
    monkeypatch.setattr(caller_assistant, "require_csrf", lambda request, token: None)

    response = caller_assistant.update_lead_requirements(
        lead_id=lead.id, request=_post_request(), customer_name="Qualification Customer",
        mobile="9876509876", alternate_mobile="", email="buyer@example.com", customer_notes="Evening calls",
        requirement_text="Family home near station", budget_min="7000000", budget_max="10000000",
        preferred_locations="Borivali", bhk="2 BHK", property_type="Apartment", buy_rent="BUY",
        property_category="Residential", carpet_area_min="650", carpet_area_max="900",
        possession_requirement="Within 1 Year", furnishing="Semi-Furnished", parking="1 covered",
        project_preference="Near station", developer_preference="Preferred developer",
        loan_required=True, purpose="Self Use", requirement_notes="Loan pre-approval pending",
        csrf_token_value="test", db=db_session,
    )

    assert response.status_code == 303
    requirement = db_session.query(CustomerRequirement).filter_by(customer_id=customer.id, is_active=True).one()
    assert str(requirement.carpet_area_min) == "650.00"
    assert str(requirement.carpet_area_max) == "900.00"
    assert requirement.property_category == "Residential"
    assert requirement.possession_requirement == "Within 1 Year"
    assert requirement.furnishing == "Semi-Furnished"
    assert requirement.parking == "1 covered"
    assert requirement.project_preference == "Near station"
    assert requirement.developer_preference == "Preferred developer"
    assert requirement.loan_required is True
    assert requirement.purpose == "Self Use"


def test_sales_executive_rejects_reversed_carpet_area_range(db_session, monkeypatch):
    import pytest
    from app.models import Customer, Lead, User
    from app.routers import caller_assistant

    actor = User(username="sales-area-range", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Area Customer", mobile="9876501122")
    db_session.add_all([actor, customer])
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="NEW", assigned_user_id=actor.id)
    db_session.add(lead)
    db_session.commit()
    monkeypatch.setattr(caller_assistant, "_current_user", lambda request, db: actor)
    monkeypatch.setattr(caller_assistant, "require_csrf", lambda request, token: None)

    response = caller_assistant.update_lead_requirements(
        lead_id=lead.id, request=_post_request(), customer_name="Area Customer",
        budget_min="", budget_max="", preferred_locations="", bhk="", property_type="", buy_rent="",
        property_category="", carpet_area_min="1000", carpet_area_max="500", possession_requirement="",
        furnishing="", parking="", project_preference="", developer_preference="", loan_required=False, purpose="",
        csrf_token_value="test", db=db_session,
    )

    assert response.status_code == 400
    assert "Minimum carpet area" in response.body.decode()



def test_property_calling_speech_includes_developer_and_furnishing_details():
    from app.routers.caller_assistant import _property_speeches

    speeches = _property_speeches(
        {"project": "Harbour View", "developer": "Acme Group", "property_type": "Apartment",
         "furnishing": "Semi-Furnished", "parking": "1 covered", "bhk": "2 BHK",
         "price": 8000000, "carpet_area": 750, "possession": "Ready to Move", "rera": "RERA-123"},
        {"name": "Test Customer"},
    )

    assert any("Acme Group" in text for text in speeches.values())
    assert any("Apartment" in text for text in speeches.values())
    assert any("Semi-Furnished" in text for text in speeches.values())
