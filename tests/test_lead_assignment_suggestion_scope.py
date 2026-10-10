from app.models import Lead, User
from app.routers.lead_assignment_suggestions import _scope, _visible_leads


def _user(username, role, team=None, manager_id=None):
    return User(
        username=username,
        password_hash="test-hash",
        role=role,
        team=team,
        reporting_manager_id=manager_id,
        is_active=True,
        is_approved=True,
    )


def test_team_lead_candidates_and_leads_are_scoped_to_team(db_session):
    team_lead = _user("tl-one", "TL", team="North")
    db_session.add(team_lead)
    db_session.flush()
    caller_same_team = _user("caller-north", "TELECALLER", team="North")
    caller_report = _user("caller-report", "SALES_EXECUTIVE", team="South", manager_id=team_lead.id)
    caller_other = _user("caller-south", "TELECALLER", team="South")
    db_session.add_all([caller_same_team, caller_report, caller_other])
    db_session.flush()

    owned = Lead(source="website", status="NEW", assigned_user_id=caller_same_team.id)
    other = Lead(source="website", status="NEW", assigned_user_id=caller_other.id)
    unassigned = Lead(source="website", status="NEW", assigned_user_id=None)
    db_session.add_all([owned, other, unassigned])
    db_session.flush()

    candidates, scope = _scope(team_lead, db_session)
    visible = _visible_leads(team_lead, db_session, scope)

    assert {user.id for user in candidates} == {caller_same_team.id, caller_report.id}
    assert {lead.id for lead in visible} == {owned.id}
    assert other.id not in {lead.id for lead in visible}
    assert unassigned.id not in {lead.id for lead in visible}


def test_admin_scope_can_review_unassigned_leads(db_session):
    admin = _user("admin-one", "ADMIN")
    caller = _user("caller-one", "TELECALLER")
    db_session.add_all([admin, caller])
    db_session.flush()
    unassigned = Lead(source="website", status="NEW", assigned_user_id=None)
    db_session.add(unassigned)
    db_session.flush()

    candidates, scope = _scope(admin, db_session)
    visible = _visible_leads(admin, db_session, scope)

    assert [user.id for user in candidates] == [caller.id]
    assert scope is None
    assert unassigned.id in {lead.id for lead in visible}
