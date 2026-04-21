from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .db import SessionLocal
from .sources.app_exports import AppExportsCollector
from .sources.qkb_notices import QkbNoticesCollector
from .sources.qkb_search import QkbSearchCollector

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone="Europe/Tirane")
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

    if settings.scheduler_enable_qkb_notices:
        scheduler.add_job(
            _run_qkb_notices,
            IntervalTrigger(hours=settings.scheduler_qkb_notices_interval_hours),
            id="qkb_notices_interval",
            replace_existing=True,
        )
        active_jobs.append(
            f"qkb_notices_interval_every_{settings.scheduler_qkb_notices_interval_hours}h"
        )

    logger.info("Scheduler started with jobs: %s", ", ".join(active_jobs) or "none")
    scheduler.start()


def _run_app_exports() -> None:
    logger.info("Scheduled job: APP exports")
    with SessionLocal() as db:
        AppExportsCollector().collect(db)


def _run_qkb_notices() -> None:
    logger.info("Scheduled job: QKB notices (experimental)")
    with SessionLocal() as db:
        QkbNoticesCollector().collect(db, use_playwright=True)


def _run_qkb_search() -> None:
    logger.info("Scheduled job: QKB search")
    with SessionLocal() as db:
        today = date.today()
        lookback_days = max(0, settings.scheduler_qkb_search_lookback_days)
        start_date = today - timedelta(days=lookback_days)
        QkbSearchCollector().collect(db, data_nga=start_date, data_ne=today)
