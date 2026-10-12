"""Standalone reminder scheduler entry point; never run inside web lifespan."""
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import settings
from app.database import SessionLocal
from app import models  # noqa: F401
from app import reminder_models  # noqa: F401
from app import site_visit_workflow_models  # noqa: F401
from app.services.automatic_reminders import process_due_reminders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_once():
    db = SessionLocal()
    try:
        result = process_due_reminders(db)
        logger.info("Automatic reminder cycle: %s", result)
        return result
    finally:
        db.close()

def main():
    scheduler = BlockingScheduler(timezone=settings.backup_timezone)
    scheduler.add_job(run_once, IntervalTrigger(minutes=5, timezone=settings.backup_timezone),
        id="metrocrm_automatic_reminders", replace_existing=True, max_instances=1,
        coalesce=True, misfire_grace_time=240)
    logger.info("MetroCRM automatic reminder worker starting; timezone=%s", settings.backup_timezone)
    run_once()
    scheduler.start()

if __name__ == "__main__":
    main()
