"""Twice-daily secure backup scheduler with automatic catch-up retries."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.backup import create_full_backup, retry_pending_backups

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _retry_job() -> None:
    try:
        results = retry_pending_backups()
        if results:
            logger.info("MetroCRM backup retry completed: %s backup states processed", len(results))
    except Exception:
        logger.exception("MetroCRM backup retry job failed")


def _scheduled_backup(label: str) -> None:
    try:
        result = create_full_backup(label)
        logger.info("MetroCRM scheduled backup %s completed with status=%s", label, result.get("status"))
    except Exception:
        logger.exception("MetroCRM scheduled backup %s failed", label)


def start_backup_scheduler() -> None:
    global _scheduler
    if not settings.backup_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=settings.backup_timezone)
    # One-hour misfire grace prevents a service restart/deploy near the scheduled
    # time from silently losing that backup cycle. max_instances=1 prevents overlap.
    _scheduler.add_job(
        lambda: _scheduled_backup("start"),
        CronTrigger(hour=11, minute=0, timezone=settings.backup_timezone),
        id="metrocrm_backup_start", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    _scheduler.add_job(
        lambda: _scheduled_backup("end"),
        CronTrigger(hour=19, minute=0, timezone=settings.backup_timezone),
        id="metrocrm_backup_end", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _retry_job,
        CronTrigger(minute="*/10", timezone=settings.backup_timezone),
        id="metrocrm_backup_retry", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info("MetroCRM backup scheduler started: 11:00, 19:00, retries every 10 minutes (%s)", settings.backup_timezone)


def stop_backup_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("MetroCRM backup scheduler stopped")
