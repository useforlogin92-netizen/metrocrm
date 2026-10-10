import pytest
from fastapi import HTTPException

from app.models import Customer, Lead, User
from app.routers.email import _lead_for_user as email_lead_for_user
from app.routers.whatsapp import _lead_for_user as whatsapp_lead_for_user


@pytest.mark.parametrize("lead_for_user", [email_lead_for_user, whatsapp_lead_for_user])
def test_messaging_allows_manager_reporting_tree_and_denies_other_teams(db_session, lead_for_user):
    manager = User(username="message-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    team_lead = User(username="message-tl", password_hash="x", role="TL", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    db_session.add(team_lead)
    db_session.flush()
    executive = User(username="message-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=team_lead.id, is_active=True, is_approved=True)
    outsider = User(username="message-outsider", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Team Customer", mobile="9876501234", email="team@example.com")
    other_customer = Customer(name="Outside Customer", mobile="9876504321", email="outside@example.com")
    db_session.add_all([executive, outsider, customer, other_customer])
    db_session.flush()
    assigned = Lead(customer_id=customer.id, source="WEBSITE", status="NEW", assigned_user_id=executive.id)
    outside = Lead(customer_id=other_customer.id, source="WEBSITE", status="NEW", assigned_user_id=outsider.id)
    db_session.add_all([assigned, outside])
    db_session.commit()

    lead, linked_customer = lead_for_user(assigned.id, manager, db_session)
    assert lead.id == assigned.id
    assert linked_customer.id == customer.id
    with pytest.raises(HTTPException) as exc:
        lead_for_user(outside.id, manager, db_session)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("lead_for_user", [email_lead_for_user, whatsapp_lead_for_user])
def test_sales_executive_cannot_message_another_executives_lead(db_session, lead_for_user):
    first = User(username="message-first", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    second = User(username="message-second", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    customer = Customer(name="Private Customer", mobile="9876512345", email="private@example.com")
    db_session.add_all([first, second, customer])
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="NEW", assigned_user_id=second.id)
    db_session.add(lead)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        lead_for_user(lead.id, first, db_session)
    assert exc.value.status_code == 403
