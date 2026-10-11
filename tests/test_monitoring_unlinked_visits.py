from datetime import datetime

from app.models import SiteVisit, User
from app.routers.lead_visit_monitoring import _site_visits_in_scope_query


def _user(db_session, username: str) -> User:
    user = User(username=username, password_hash="test-hash", role="TELECALLER", is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


def test_scoped_monitoring_includes_assigned_visit_without_linked_lead(db_session):
    caller = _user(db_session, "unlinked-visit-caller")
    other_caller = _user(db_session, "unlinked-visit-other-caller")
    assigned_visit = SiteVisit(
        lead_id=None,
        sales_employee_id=caller.id,
        scheduled_at=datetime(2026, 10, 12, 10, 0),
        status="SCHEDULED",
    )
    out_of_scope_visit = SiteVisit(
        lead_id=None,
        sales_employee_id=other_caller.id,
        scheduled_at=datetime(2026, 10, 12, 11, 0),
        status="SCHEDULED",
    )
    db_session.add_all([assigned_visit, out_of_scope_visit])
    db_session.flush()

    visits = db_session.scalars(_site_visits_in_scope_query({caller.id})).all()

    assert [visit.id for visit in visits] == [assigned_visit.id]
