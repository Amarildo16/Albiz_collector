from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .db import SessionLocal
from .sources.app_exports import AppExportsCollector
from .sources.qkb_search import QkbSearchCollector

logger = logging.getLogger(__name__)
SCHEDULER_TIMEZONE = ZoneInfo("Europe/Tirane")


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=SCHEDULER_TIMEZONE)
    active_jobs: list[str] = []

    scheduler.add_job(
        _run_app_exports,
        CronTrigger(hour=settings.scheduler_app_exports_hour, minute=0),
        id="app_exports_daily",
        replace_existing=True,
    )
    active_jobs.append(f"app_exports_daily@{settings.scheduler_app_exports_hour:02d}:00")

    if settings.scheduler_enable_qkb_search:
        scheduler.add_job(
            _run_qkb_search,
            CronTrigger(hour=settings.scheduler_qkb_search_hour, minute=15),
            id="qkb_search_daily",
            replace_existing=True,
        )
        active_jobs.append(
            "qkb_search_daily@"
            f"{settings.scheduler_qkb_search_hour:02d}:15"
            f"(lookback_days={settings.scheduler_qkb_search_lookback_days})"
        )

    logger.info("Scheduler started with jobs: %s", ", ".join(active_jobs) or "none")
    scheduler.start()


def _run_app_exports() -> None:
    logger.info("Scheduled job: APP exports")
    with SessionLocal() as db:
        AppExportsCollector().collect(db)


def _scheduler_today(now: datetime | None = None) -> date:
    if now is None:
        return datetime.now(SCHEDULER_TIMEZONE).date()
    if now.tzinfo is None:
        raise ValueError("scheduler reference time must be timezone-aware")
    return now.astimezone(SCHEDULER_TIMEZONE).date()


def _qkb_search_window(now: datetime | None = None) -> tuple[date, date]:
    today = _scheduler_today(now)
    lookback_days = max(0, settings.scheduler_qkb_search_lookback_days)
    return today - timedelta(days=lookback_days), today


def _run_qkb_search(now: datetime | None = None) -> None:
    logger.info("Scheduled job: QKB search")
    with SessionLocal() as db:
        start_date, end_date = _qkb_search_window(now=now)
        QkbSearchCollector().collect(db, data_nga=start_date, data_ne=end_date)
