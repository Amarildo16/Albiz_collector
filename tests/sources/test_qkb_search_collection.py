from __future__ import annotations

import json
import re
import unittest
from datetime import date

from sqlalchemy import select
from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.db import Base
from albiz_collector.models import QkbSearchRun, RawFetch, StructuredRecord
from albiz_collector.sources.qkb_search import (
    QkbSearchCollector,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_INTERRUPTED,
)
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _record_batch(count: int, *, prefix: str) -> list[dict[str, str]]:
    return [{"nipti": f"{prefix}{index:03d}"} for index in range(1, count + 1)]


def _window_key(
    *,
    nipt: str | None = None,
    data_nga: str = "",
    data_ne: str = "",
) -> tuple[str, str, str]:
    return (nipt or "", data_nga, data_ne)


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


class _FakeHttpClient:
    def __init__(self, responses: dict[tuple[str, str, str], list[dict[str, str]] | Exception]) -> None:
        self._responses = responses
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> ResponsePayload:
        self.get_calls.append(url)
        content = b"<html><body>qkb search session bootstrap</body></html>"
        return ResponsePayload(
            url=url,
            status_code=200,
            content_type="text/html",
            content=content,
            text=content.decode("utf-8"),
            cookies=None,
        )

    def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies=None,
    ) -> ResponsePayload:
        request_data = dict(data or {})
        self.post_calls.append(
            {
                "url": url,
                "data": request_data,
                "headers": headers or {},
                "cookies": cookies,
            }
        )
        key = _window_key(
            nipt=request_data.get("nipt"),
            data_nga=request_data.get("dataNga", ""),
            data_ne=request_data.get("dataNe", ""),
        )
        if key not in self._responses:
            raise AssertionError(f"Unexpected QKB search request: {key!r}")

        result = self._responses[key]
        if isinstance(result, Exception):
            raise result

        content = _build_html(result)
        return ResponsePayload(
            url=url,
            status_code=200,
            content_type="text/html",
            content=content,
            text=content.decode("utf-8"),
            cookies=None,
        )


class _TestQkbSearchCollector(QkbSearchCollector):
    def __init__(self, http_client: _FakeHttpClient) -> None:
        self._fake_http_client = http_client

    def _http_client(self) -> _FakeHttpClient:
        return self._fake_http_client


class QkbSearchCollectionTests(unittest.TestCase):
    def test_qkb_search_cli_help_mentions_restart_and_not_playwright(self) -> None:
        runner = CliRunner()

        result = runner.invoke(app, ["run", "qkb-search", "--help"])
        clean_stdout = _strip_ansi(result.stdout).lower()

        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("playwright", clean_stdout)
        self.assertIn("restart", clean_stdout)
        self.assertIn("nipt", clean_stdout)
        self.assertIn("data-nga", clean_stdout)
        self.assertIn("data-ne", clean_stdout)

    def test_date_range_search_creates_new_resumable_run_and_chunks_inclusive_days(self) -> None:
        http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): _record_batch(1, prefix="B"),
                _window_key(data_nga="03/01/2025", data_ne="03/01/2025"): _record_batch(1, prefix="C"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                )
                structured_records = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()
                runs = db.scalars(select(QkbSearchRun).order_by(QkbSearchRun.id)).all()

        self.assertEqual(len(http.get_calls), 1)
        self.assertEqual(
            [call["data"] for call in http.post_calls],
            [
                {
                    "orderColumn": "0",
                    "orderDir": "asc",
                    "nipt": "",
                    "emriISubjektit": "",
                    "emriTregtar": "",
                    "formeLigjore": "",
                    "pronesia": "",
                    "dataNga": "01/01/2025",
                    "dataNe": "01/01/2025",
                    "numriId": "",
                    "administrator": "",
                    "aksionerOrtak": "",
                    "sektoriIVeprimtarise": "",
                    "qarku": "",
                    "qyteti": "",
                    "adresa": "",
                },
                {
                    "orderColumn": "0",
                    "orderDir": "asc",
                    "nipt": "",
                    "emriISubjektit": "",
                    "emriTregtar": "",
                    "formeLigjore": "",
                    "pronesia": "",
                    "dataNga": "02/01/2025",
                    "dataNe": "02/01/2025",
                    "numriId": "",
                    "administrator": "",
                    "aksionerOrtak": "",
                    "sektoriIVeprimtarise": "",
                    "qarku": "",
                    "qyteti": "",
                    "adresa": "",
                },
                {
                    "orderColumn": "0",
                    "orderDir": "asc",
                    "nipt": "",
                    "emriISubjektit": "",
                    "emriTregtar": "",
                    "formeLigjore": "",
                    "pronesia": "",
                    "dataNga": "03/01/2025",
                    "dataNe": "03/01/2025",
                    "numriId": "",
                    "administrator": "",
                    "aksionerOrtak": "",
                    "sektoriIVeprimtarise": "",
                    "qarku": "",
                    "qyteti": "",
                    "adresa": "",
                },
            ],
        )
        self.assertEqual(result["search_mode"], "daily_range")
        self.assertEqual(result["run_start_behavior"], "starting_new")
        self.assertEqual(result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(result["requested_range_days"], 3)
        self.assertEqual(result["search_requests_executed"], 3)
        self.assertEqual(result["total_days_searched"], 3)
        self.assertEqual(result["successful_day_searches"], 3)
        self.assertEqual(result["failed_day_searches"], 0)
        self.assertEqual(result["days_previously_completed_before_run"], 0)
        self.assertEqual(result["days_completed_total"], 3)
        self.assertEqual(result["days_remaining_after_run"], 0)
        self.assertEqual(result["days_returning_exactly_50_results"], 0)
        self.assertEqual(result["total_raw_rows_found"], 3)
        self.assertEqual(result["total_unique_persisted_snapshots"], 3)
        self.assertEqual(len(result["per_day_summaries"]), 3)
        self.assertEqual(
            [record.external_key for record in structured_records],
            [
                "all|2025-01-01|2025-01-01",
                "all|2025-01-02|2025-01-02",
                "all|2025-01-03|2025-01-03",
            ],
        )
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].current_date, None)
        self.assertEqual(runs[0].status, RUN_STATUS_COMPLETED)

    def test_single_day_range_executes_one_one_day_search(self) -> None:
        http = _FakeHttpClient(
            {
                _window_key(data_nga="05/01/2025", data_ne="05/01/2025"): _record_batch(2, prefix="D"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2025, 1, 5),
                    data_ne=date(2025, 1, 5),
                )

        self.assertEqual(len(http.post_calls), 1)
        self.assertEqual(http.post_calls[0]["data"]["dataNga"], "05/01/2025")
        self.assertEqual(http.post_calls[0]["data"]["dataNe"], "05/01/2025")
        self.assertEqual(result["search_mode"], "daily_range")
        self.assertEqual(result["total_days_searched"], 1)
        self.assertEqual(result["successful_day_searches"], 1)
        self.assertEqual(result["failed_day_searches"], 0)
        self.assertEqual(result["records_found"], 2)

    def test_nipt_search_with_date_range_remains_single_http_request_and_has_no_run_state(self) -> None:
        http = _FakeHttpClient(
            {
                _window_key(
                    nipt="M21528028T",
                    data_nga="01/01/2025",
                    data_ne="03/01/2025",
                ): _record_batch(1, prefix="N"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect(
                    db,
                    nipt="M21528028T",
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                )
                structured_records = db.scalars(select(StructuredRecord)).all()
                runs = db.scalars(select(QkbSearchRun)).all()

        self.assertEqual(len(http.post_calls), 1)
        self.assertEqual(http.post_calls[0]["data"]["nipt"], "M21528028T")
        self.assertEqual(http.post_calls[0]["data"]["dataNga"], "01/01/2025")
        self.assertEqual(http.post_calls[0]["data"]["dataNe"], "03/01/2025")
        self.assertEqual(result["search_mode"], "single")
        self.assertFalse(result["date_chunking_applied"])
        self.assertEqual(result["requested_range_days"], 3)
        self.assertEqual(result["search_requests_executed"], 1)
        self.assertEqual(result["total_days_searched"], 0)
        self.assertEqual(result["successful_day_searches"], 0)
        self.assertEqual(result["failed_day_searches"], 0)
        self.assertEqual(result["records_found"], 1)
        self.assertEqual(len(structured_records), 1)
        self.assertEqual(structured_records[0].external_key, "M21528028T|2025-01-01|2025-01-03")
        self.assertEqual(runs, [])

    def test_daily_range_reports_potential_truncation_when_day_hits_limit(self) -> None:
        http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(50, prefix="L"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): _record_batch(1, prefix="S"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 2),
                )

        self.assertEqual(result["days_returning_exactly_50_results"], 1)
        self.assertEqual(result["potentially_truncated_days"], ["2025-01-01"])
        self.assertEqual(result["total_raw_rows_found"], 51)
        self.assertTrue(result["per_day_summaries"][0]["potentially_truncated"])
        self.assertFalse(result["per_day_summaries"][1]["potentially_truncated"])

    def test_progress_only_advances_after_successful_day_and_resume_continues_from_failed_day(self) -> None:
        first_http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): RuntimeError("day 2 failed"),
            }
        )
        second_http = _FakeHttpClient(
            {
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): _record_batch(1, prefix="B"),
                _window_key(data_nga="03/01/2025", data_ne="03/01/2025"): _record_batch(1, prefix="C"),
            }
        )
        first_collector = _TestQkbSearchCollector(first_http)
        second_collector = _TestQkbSearchCollector(second_http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                first_result = first_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                )
                failed_run = db.scalar(select(QkbSearchRun))
                structured_after_failure = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()
                raw_fetches_after_failure = db.scalars(select(RawFetch).order_by(RawFetch.id)).all()
                assert failed_run is not None
                failed_run_id = failed_run.id
                failed_run_current_date = failed_run.current_date
                failed_run_status = failed_run.status

                second_result = second_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                )
                resumed_run = db.scalar(select(QkbSearchRun))
                structured_after_resume = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()

        assert resumed_run is not None
        self.assertEqual(first_result["run_status"], RUN_STATUS_FAILED)
        self.assertEqual(first_result["run_current_date"], "2025-01-02")
        self.assertEqual(first_result["days_previously_completed_before_run"], 0)
        self.assertEqual(first_result["days_completed_total"], 1)
        self.assertEqual(first_result["days_remaining_after_run"], 2)
        self.assertEqual(first_result["failed_day_searches"], 1)
        self.assertEqual(first_result["search_requests_executed"], 2)
        self.assertEqual(len(structured_after_failure), 1)
        self.assertEqual(len(raw_fetches_after_failure), 1)
        assert failed_run_current_date is not None
        self.assertEqual(failed_run_current_date.isoformat(), "2025-01-02")
        self.assertEqual(failed_run_status, RUN_STATUS_FAILED)

        self.assertEqual(second_result["run_start_behavior"], "resuming_existing")
        self.assertEqual(second_result["resume_from_date"], "2025-01-02")
        self.assertEqual(second_result["run_id"], failed_run_id)
        self.assertEqual(second_result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(second_result["successful_day_searches"], 2)
        self.assertEqual(second_result["days_previously_completed_before_run"], 1)
        self.assertEqual(second_result["days_completed_total"], 3)
        self.assertEqual(second_result["days_remaining_after_run"], 0)
        self.assertEqual(len(second_http.post_calls), 2)
        self.assertEqual(
            [call["data"]["dataNga"] for call in second_http.post_calls],
            ["02/01/2025", "03/01/2025"],
        )
        self.assertEqual(len(structured_after_resume), 3)
        self.assertEqual(resumed_run.current_date, None)
        self.assertEqual(resumed_run.status, RUN_STATUS_COMPLETED)

    def test_restart_from_scratch_marks_old_run_interrupted_and_starts_new_run(self) -> None:
        first_http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): RuntimeError("day 2 failed"),
            }
        )
        restarted_http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): _record_batch(1, prefix="B"),
                _window_key(data_nga="03/01/2025", data_ne="03/01/2025"): _record_batch(1, prefix="C"),
            }
        )
        first_collector = _TestQkbSearchCollector(first_http)
        restarted_collector = _TestQkbSearchCollector(restarted_http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                failed_result = first_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                )
                failed_run = db.scalar(select(QkbSearchRun))

                restarted_result = restarted_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                    restart=True,
                )
                runs = db.scalars(select(QkbSearchRun).order_by(QkbSearchRun.id)).all()
                structured_records = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()

        assert failed_run is not None
        self.assertEqual(failed_result["run_status"], RUN_STATUS_FAILED)
        self.assertEqual(restarted_result["run_start_behavior"], "restarting_from_scratch")
        self.assertEqual(restarted_result["resume_from_date"], "2025-01-01")
        self.assertEqual(restarted_result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(len(restarted_http.post_calls), 3)
        self.assertEqual(
            [call["data"]["dataNga"] for call in restarted_http.post_calls],
            ["01/01/2025", "02/01/2025", "03/01/2025"],
        )
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].status, RUN_STATUS_INTERRUPTED)
        self.assertEqual(runs[1].status, RUN_STATUS_COMPLETED)
        self.assertNotEqual(runs[0].id, runs[1].id)
        self.assertEqual(restarted_result["run_id"], runs[1].id)
        self.assertEqual(len(structured_records), 3)

    def test_different_date_range_creates_new_run_instead_of_resuming(self) -> None:
        first_http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): RuntimeError("day 2 failed"),
            }
        )
        second_http = _FakeHttpClient(
            {
                _window_key(data_nga="04/01/2025", data_ne="04/01/2025"): _record_batch(1, prefix="D"),
                _window_key(data_nga="05/01/2025", data_ne="05/01/2025"): _record_batch(1, prefix="E"),
            }
        )
        first_collector = _TestQkbSearchCollector(first_http)
        second_collector = _TestQkbSearchCollector(second_http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                first_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 3),
                )
                result = second_collector.collect(
                    db,
                    data_nga=date(2025, 1, 4),
                    data_ne=date(2025, 1, 5),
                )
                runs = db.scalars(select(QkbSearchRun).order_by(QkbSearchRun.id)).all()

        self.assertEqual(result["run_start_behavior"], "starting_new")
        self.assertEqual(len(second_http.post_calls), 2)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].status, RUN_STATUS_FAILED)
        self.assertEqual(runs[1].status, RUN_STATUS_COMPLETED)

    def test_completed_runs_are_not_resumed_again(self) -> None:
        first_http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): _record_batch(1, prefix="B"),
            }
        )
        second_http = _FakeHttpClient(
            {
                _window_key(data_nga="01/01/2025", data_ne="01/01/2025"): _record_batch(1, prefix="A"),
                _window_key(data_nga="02/01/2025", data_ne="02/01/2025"): _record_batch(1, prefix="B"),
            }
        )
        first_collector = _TestQkbSearchCollector(first_http)
        second_collector = _TestQkbSearchCollector(second_http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                first_result = first_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 2),
                )
                second_result = second_collector.collect(
                    db,
                    data_nga=date(2025, 1, 1),
                    data_ne=date(2025, 1, 2),
                )
                runs = db.scalars(select(QkbSearchRun).order_by(QkbSearchRun.id)).all()

        self.assertEqual(first_result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(second_result["run_start_behavior"], "starting_new")
        self.assertEqual(second_result["run_status"], RUN_STATUS_COMPLETED)
        self.assertNotEqual(first_result["run_id"], second_result["run_id"])
        self.assertEqual(len(second_http.post_calls), 2)
        self.assertEqual(len(runs), 2)
        self.assertTrue(all(run.status == RUN_STATUS_COMPLETED for run in runs))


if __name__ == "__main__":
    unittest.main()
