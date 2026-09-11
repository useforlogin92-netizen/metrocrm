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
                    ids = set(stmt.compile().params.values())
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
    speeches = _opening_speeches(
        user,
        lead,
        customer,
        [{"name":"Borivali","side":"Both","priority":"Primary"},{"name":"Andheri","side":"Both","priority":"Primary"}],
    )
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
