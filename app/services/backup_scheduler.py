"""Twice-daily secure backup scheduler with automatic catch-up retries."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.backup import create_full_backup, retry_pending_backups

_scheduler: BackgroundScheduler | None = None


def _retry_job() -> None:
    try:
        retry_pending_backups()
    except Exception:
        # A retry must never stop the scheduler; the next interval will try again.
        pass


def _scheduled_backup(label: str) -> None:
    try:
        create_full_backup(label)
    except Exception:
        # The local snapshot failure is visible in server logs; scheduler stays alive.
        pass


def start_backup_scheduler() -> None:
    global _scheduler
    if not settings.backup_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=settings.backup_timezone)
    _scheduler.add_job(
        lambda: _scheduled_backup("start"),
        CronTrigger(hour=11, minute=0, timezone=settings.backup_timezone),
        id="metrocrm_backup_start", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        lambda: _scheduled_backup("end"),
        CronTrigger(hour=19, minute=0, timezone=settings.backup_timezone),
        id="metrocrm_backup_end", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        _retry_job,
        CronTrigger(minute="*/10", timezone=settings.backup_timezone),
        id="metrocrm_backup_retry", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.start()


def stop_backup_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
