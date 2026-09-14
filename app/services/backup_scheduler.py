"""Twice-daily secure backup scheduler with catch-up retries and failure alerts."""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.backup import create_full_backup, retry_pending_backups
from app.services.backup_alerts import notify_backup_failure

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
_last_missed_alert: str | None = None


def _retry_job() -> None:
    global _last_missed_alert
    try:
        results = retry_pending_backups()
        if results:
            logger.info("MetroCRM backup retry completed: %s backup states processed", len(results))
            for result in results:
                if result.get("status") != "success":
                    notify_backup_failure(result, "backup_destination_retry_still_failed")

        now = datetime.now().astimezone()
        grace = max(0, settings.backup_missed_cycle_grace_minutes)
        expected_label = "start" if now.hour == 11 and now.minute >= grace else "end" if now.hour == 19 and now.minute >= grace else None
        if expected_label:
            today = now.strftime("%Y-%m-%d")
            marker = f"{today}:{expected_label}"
            successful = any(
                str(item.get("created_at", "")).startswith(today)
                and str(item.get("label", "")) == expected_label
                and str(item.get("status", "")) == "success"
                for item in results
            )
            if not successful and _last_missed_alert != marker:
                notify_backup_failure({"status": "failed", "date": today, "label": expected_label, "failed_destinations": ["scheduled_cycle"]}, "scheduled_backup_cycle_missing_after_grace_period")
                _last_missed_alert = marker
    except Exception:
        logger.exception("MetroCRM backup retry/missed-cycle check failed")


def _scheduled_backup(label: str) -> None:
    try:
        result = create_full_backup(label)
        logger.info("MetroCRM scheduled backup %s completed with status=%s", label, result.get("status"))
        if result.get("status") != "success":
            notify_backup_failure(result, "scheduled_backup_partial_or_failed")
    except Exception as exc:
        logger.exception("MetroCRM scheduled backup %s failed", label)
        notify_backup_failure({"status": "failed", "label": label, "failed_destinations": ["backup_creation"]}, f"scheduled_backup_exception:{exc}")


def start_backup_scheduler() -> None:
    global _scheduler
    if not settings.backup_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=settings.backup_timezone)
    _scheduler.add_job(lambda: _scheduled_backup("start"), CronTrigger(hour=11, minute=0, timezone=settings.backup_timezone), id="metrocrm_backup_start", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=3600)
    _scheduler.add_job(lambda: _scheduled_backup("end"), CronTrigger(hour=19, minute=0, timezone=settings.backup_timezone), id="metrocrm_backup_end", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=3600)
    _scheduler.add_job(_retry_job, CronTrigger(minute="*/10", timezone=settings.backup_timezone), id="metrocrm_backup_retry", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
    _scheduler.start()
    logger.info("MetroCRM backup scheduler started: 11:00, 19:00, retries every 10 minutes (%s)", settings.backup_timezone)


def stop_backup_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("MetroCRM backup scheduler stopped")
