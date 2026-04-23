from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

from albiz_collector import scheduler
from albiz_collector.config import settings


@contextmanager
def _temporary_lookback_days(value: int):
    original = settings.scheduler_qkb_search_lookback_days
    settings.scheduler_qkb_search_lookback_days = value
    try:
        yield
    finally:
        settings.scheduler_qkb_search_lookback_days = original


class SchedulerTimezoneTests(unittest.TestCase):
    def test_scheduler_today_uses_tirane_timezone(self) -> None:
        reference_time = datetime(2026, 4, 23, 22, 30, tzinfo=timezone.utc)

        today = scheduler._scheduler_today(reference_time)

        self.assertEqual(today.isoformat(), "2026-04-24")

    def test_qkb_search_window_uses_tirane_date_for_lookback(self) -> None:
        reference_time = datetime(2026, 4, 23, 22, 30, tzinfo=timezone.utc)

        with _temporary_lookback_days(2):
            start_date, end_date = scheduler._qkb_search_window(now=reference_time)

        self.assertEqual(start_date.isoformat(), "2026-04-22")
        self.assertEqual(end_date.isoformat(), "2026-04-24")

    def test_run_qkb_search_passes_tirane_window_to_collector(self) -> None:
        captured: dict[str, object] = {}
        reference_time = datetime(2026, 4, 23, 22, 30, tzinfo=timezone.utc)

        class _Collector:
            def collect(self, db, *, data_nga, data_ne):
                captured["db"] = db
                captured["data_nga"] = data_nga
                captured["data_ne"] = data_ne

        @contextmanager
        def _fake_session_local():
            yield "db-session"

        with _temporary_lookback_days(1):
            with patch.object(scheduler, "QkbSearchCollector", return_value=_Collector()):
                with patch.object(scheduler, "SessionLocal", _fake_session_local):
                    scheduler._run_qkb_search(now=reference_time)

        self.assertEqual(captured["db"], "db-session")
        self.assertEqual(captured["data_nga"].isoformat(), "2026-04-23")
        self.assertEqual(captured["data_ne"].isoformat(), "2026-04-24")


if __name__ == "__main__":
    unittest.main()
