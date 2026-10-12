"""Idempotent staff reminders for due follow-ups and upcoming site visits.

This module notifies assigned CRM employees only, never customers. Run it as a
single dedicated worker, not from the web application's lifespan.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Customer, FollowUp, Lead, SiteVisit, User
from app.reminder_models import ReminderDelivery
from app.services.email import send_email
from app.services.whatsapp import send_text

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 6
RETRY_MINUTES = (1, 5, 15, 30, 60, 120)

def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value

def _key(event_type: str, event_id: int, due_at: datetime, stage: str, user_id: int, channel: str) -> str:
    due = _naive_utc(due_at).isoformat(timespec="seconds")
    return f"{event_type}:{event_id}:{due}:{stage}:{user_id}:{channel}"

def _queue(db: Session, *, event_type: str, event_id: int, due_at: datetime,
           stage: str, user: User, channel: str, now: datetime) -> ReminderDelivery | None:
    key = _key(event_type, event_id, due_at, stage, user.id, channel)
    existing = db.scalar(select(ReminderDelivery).where(ReminderDelivery.reminder_key == key))
    if existing:
        return existing
    delivery = ReminderDelivery(reminder_key=key, event_type=event_type, event_id=event_id,
        recipient_user_id=user.id, channel=channel, status="PENDING", attempts=0, next_attempt_at=now)
    db.add(delivery)
    try:
        db.commit()
        db.refresh(delivery)
        return delivery
    except IntegrityError:
        db.rollback()
        return db.scalar(select(ReminderDelivery).where(ReminderDelivery.reminder_key == key))

def _recipient(user: User) -> str | None:
    if user.email and "@" in user.email:
        return "email"
    if user.mobile:
        return "whatsapp"
    return None

def _deliver(db: Session, delivery: ReminderDelivery, user: User, subject: str, body: str, now: datetime) -> None:
    delivery.attempts += 1
    try:
        result = send_email(user.email or "", subject, body) if delivery.channel == "email" else send_text(user.mobile or "", body)
        status = str(result.get("status", "FAILED")).upper()
        if status in {"SENT", "TEST"}:
            delivery.status = status
            delivery.last_error = None
            delivery.sent_at = now
        else:
            raise RuntimeError(f"provider_status_{status.lower()}")
    except Exception as exc:
        delivery.last_error = str(exc)[:1000]
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "FAILED"
        else:
            delay = RETRY_MINUTES[min(delivery.attempts - 1, len(RETRY_MINUTES) - 1)]
            delivery.status = "RETRY"
            delivery.next_attempt_at = now + timedelta(minutes=delay)
        logger.warning("Reminder delivery %s failed (attempt %s): %s", delivery.id, delivery.attempts, delivery.last_error)
    delivery.updated_at = now
    db.commit()

def _notify(db: Session, *, event_type: str, event_id: int, due_at: datetime,
            stage: str, user: User, subject: str, body: str, now: datetime) -> ReminderDelivery | None:
    channel = _recipient(user)
    if not channel:
        return None
    delivery = _queue(db, event_type=event_type, event_id=event_id, due_at=due_at,
                      stage=stage, user=user, channel=channel, now=now)
    if not delivery or delivery.status in {"SENT", "TEST", "FAILED"} or delivery.next_attempt_at > now:
        return delivery
    _deliver(db, delivery, user, subject, body, now)
    return delivery

def process_due_reminders(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Queue and attempt reminders due within 30 minutes, overdue, or visits within an hour."""
    now = _naive_utc(now or datetime.now(timezone.utc))
    counts = {"queued_or_attempted": 0, "sent": 0, "retry": 0, "failed": 0, "skipped": 0}
    followups = db.scalars(select(FollowUp).where(FollowUp.completed.is_(False)).order_by(FollowUp.due_at.asc()).limit(1000)).all()
    for item in followups:
        due = _naive_utc(item.due_at)
        stage = "overdue" if due <= now else ("upcoming" if due <= now + timedelta(minutes=30) else "")
        if not stage:
            continue
        user = db.get(User, item.assigned_user_id) if item.assigned_user_id else None
        if not user or not user.is_active:
            counts["skipped"] += 1
            continue
        lead = db.get(Lead, item.lead_id) if item.lead_id else None
        customer = db.get(Customer, item.customer_id) if item.customer_id else (db.get(Customer, lead.customer_id) if lead and lead.customer_id else None)
        channel = _recipient(user)
        if not channel:
            counts["skipped"] += 1
            continue
        purpose = (item.purpose or "Call follow-up").strip()
        body = f"MetroCRM reminder: {purpose}. Due: {due.strftime('%d %b %Y %I:%M UTC')}."
        if customer:
            body += f" Customer: {customer.name}."
        if lead:
            body += f" Lead #{lead.id}."
        body += " Please update the follow-up status in MetroCRM."
        key = _key("followup", item.id, due, stage, user.id, channel)
        existed = db.scalar(select(ReminderDelivery.id).where(ReminderDelivery.reminder_key == key))
        row = _notify(db, event_type="followup", event_id=item.id, due_at=due, stage=stage,
                      user=user, subject=f"MetroCRM: {purpose}", body=body, now=now)
        counts["queued_or_attempted"] += 1
        if row and row.status in {"SENT", "TEST"} and not existed:
            counts["sent"] += 1
        elif row and row.status == "RETRY":
            counts["retry"] += 1
        elif row and row.status == "FAILED":
            counts["failed"] += 1

    visits = db.scalars(select(SiteVisit).where(SiteVisit.scheduled_at >= now,
        SiteVisit.scheduled_at <= now + timedelta(hours=1)).order_by(SiteVisit.scheduled_at.asc()).limit(1000)).all()
    for visit in visits:
        if (visit.status or "SCHEDULED").upper() in {"CANCELLED", "COMPLETED", "DONE", "NO_SHOW", "CUSTOMER_NO_SHOW"}:
            continue
        user = db.get(User, visit.sales_employee_id) if visit.sales_employee_id else None
        if user is None and visit.conducted_by_id:
            user = db.get(User, visit.conducted_by_id)
        if not user or not user.is_active:
            counts["skipped"] += 1
            continue
        customer = db.get(Customer, visit.customer_id) if visit.customer_id else None
        lead = db.get(Lead, visit.lead_id) if visit.lead_id else None
        if customer is None and lead and lead.customer_id:
            customer = db.get(Customer, lead.customer_id)
        due = _naive_utc(visit.scheduled_at)
        channel = _recipient(user)
        if not channel:
            counts["skipped"] += 1
            continue
        body = f"MetroCRM site-visit reminder: Visit #{visit.id} is scheduled for {due.strftime('%d %b %Y %I:%M UTC')}."
        if customer:
            body += f" Customer: {customer.name}."
        body += " Please confirm readiness and update the visit status in MetroCRM."
        key = _key("site_visit", visit.id, due, "upcoming", user.id, channel)
        existed = db.scalar(select(ReminderDelivery.id).where(ReminderDelivery.reminder_key == key))
        row = _notify(db, event_type="site_visit", event_id=visit.id, due_at=due, stage="upcoming",
                      user=user, subject=f"MetroCRM: Site visit #{visit.id}", body=body, now=now)
        counts["queued_or_attempted"] += 1
        if row and row.status in {"SENT", "TEST"} and not existed:
            counts["sent"] += 1
        elif row and row.status == "RETRY":
            counts["retry"] += 1
        elif row and row.status == "FAILED":
            counts["failed"] += 1
    return counts
