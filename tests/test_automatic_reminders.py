from datetime import datetime, timedelta
from app.models import Customer, FollowUp, Lead, SiteVisit, User
from app.reminder_models import ReminderDelivery
from app.services import automatic_reminders

def _user(db, **kwargs):
    user = User(username=kwargs.get("username", "caller"), password_hash="test-hash",
        role="TELECALLER", email=kwargs.get("email", "caller@example.test"),
        mobile=kwargs.get("mobile", "9876543210"), is_active=True, is_approved=True)
    db.add(user)
    db.flush()
    return user

def test_due_followup_queues_one_staff_email_and_deduplicates(db_session, monkeypatch):
    now = datetime(2026, 10, 12, 10, 0)
    user = _user(db_session)
    customer = Customer(name="Test Customer", mobile="9876543210", email="customer@example.test")
    db_session.add(customer)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="test", status="NEW", assigned_user_id=user.id)
    db_session.add(lead)
    db_session.flush()
    followup = FollowUp(lead_id=lead.id, customer_id=customer.id, assigned_user_id=user.id,
        due_at=now - timedelta(minutes=5), purpose="Call back", completed=False)
    db_session.add(followup)
    db_session.commit()
    sent = []
    monkeypatch.setattr(automatic_reminders, "send_email", lambda to, subject, body: sent.append((to, subject, body)) or {"status": "SENT"})
    first = automatic_reminders.process_due_reminders(db_session, now)
    second = automatic_reminders.process_due_reminders(db_session, now)
    assert len(sent) == 1
    assert first["sent"] == 1
    assert second["queued_or_attempted"] == 1
    assert db_session.query(ReminderDelivery).count() == 1

def test_failed_delivery_retries_after_backoff(db_session, monkeypatch):
    now = datetime(2026, 10, 12, 10, 0)
    user = _user(db_session)
    followup = FollowUp(assigned_user_id=user.id, due_at=now - timedelta(minutes=5),
        purpose="Call back", completed=False)
    db_session.add(followup)
    db_session.commit()
    calls = []
    def fail_then_succeed(*args):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("temporary gateway issue")
        return {"status": "SENT"}
    monkeypatch.setattr(automatic_reminders, "send_email", fail_then_succeed)
    automatic_reminders.process_due_reminders(db_session, now)
    row = db_session.query(ReminderDelivery).one()
    assert row.status == "RETRY"
    assert row.next_attempt_at == now + timedelta(minutes=1)
    automatic_reminders.process_due_reminders(db_session, now + timedelta(minutes=1))
    assert row.status == "SENT"
    assert row.attempts == 2

def test_upcoming_site_visit_reminds_assigned_staff_not_customer(db_session, monkeypatch):
    now = datetime(2026, 10, 12, 10, 0)
    user = _user(db_session)
    customer = Customer(name="Test Customer", mobile="9876543210", email="customer@example.test")
    db_session.add(customer)
    db_session.flush()
    visit = SiteVisit(customer_id=customer.id, sales_employee_id=user.id,
        scheduled_at=now + timedelta(minutes=20), status="SCHEDULED")
    db_session.add(visit)
    db_session.commit()
    sent = []
    monkeypatch.setattr(automatic_reminders, "send_email", lambda to, subject, body: sent.append((to, subject, body)) or {"status": "SENT"})
    result = automatic_reminders.process_due_reminders(db_session, now)
    assert result["sent"] == 1
    assert sent[0][0] == user.email
    assert "Test Customer" in sent[0][2]
    assert db_session.query(ReminderDelivery).count() == 1
