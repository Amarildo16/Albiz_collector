from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import select
from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.db import Base
from albiz_collector.models import QkbSearchRun, RawFetch, StructuredRecord
from albiz_collector.sources.qkb_search import (
    QKB_SHPK_EXTERNAL_KEY_PREFIX,
    QKB_SHPK_LEGAL_FORM_FILTER,
    QkbSearchCollector,
    RUN_MODE_DAILY_LEGAL_FORM_SHPK,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
)
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _record_batch(count: int, *, prefix: str) -> list[dict[str, str]]:
    return [{"nipti": f"{prefix}{index:03d}", "formaLigjore": "SHPK"} for index in range(1, count + 1)]


def _window_key(
    *,
    data_nga: str,
    data_ne: str,
    legal_form: str = QKB_SHPK_LEGAL_FORM_FILTER,
) -> tuple[str, str, str]:
    return (data_nga, data_ne, legal_form)


class _ShpkFakeHttpClient:
    def __init__(self, responses: dict[tuple[str, str, str], list[dict[str, str]] | Exception]) -> None:
        self._responses = responses
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_ShpkFakeHttpClient":
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
            data_nga=request_data.get("dataNga", ""),
            data_ne=request_data.get("dataNe", ""),
            legal_form=request_data.get("formeLigjore", ""),
        )
        if key not in self._responses:
            raise AssertionError(f"Unexpected SHPK QKB search request: {key!r}")

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
    def __init__(self, http_client: _ShpkFakeHttpClient) -> None:
        self._fake_http_client = http_client

    def _http_client(self) -> _ShpkFakeHttpClient:
        return self._fake_http_client


class QkbShpkUniverseCollectionTests(unittest.TestCase):
    def test_shpk_universe_daily_chunks_send_filter_and_use_distinct_external_keys(self) -> None:
        http = _ShpkFakeHttpClient(
            {
                _window_key(data_nga="02/06/2026", data_ne="02/06/2026"): _record_batch(2, prefix="A"),
                _window_key(data_nga="03/06/2026", data_ne="03/06/2026"): _record_batch(50, prefix="B"),
                _window_key(data_nga="04/06/2026", data_ne="04/06/2026"): _record_batch(1, prefix="C"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect_shpk_universe(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 4),
                )
                structured_records = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()
                raw_fetches = db.scalars(select(RawFetch).order_by(RawFetch.id)).all()
                runs = db.scalars(select(QkbSearchRun)).all()

        expected_external_keys = [
            "legal_form:SHPK|2026-06-02|2026-06-02",
            "legal_form:SHPK|2026-06-03|2026-06-03",
            "legal_form:SHPK|2026-06-04|2026-06-04",
        ]

        self.assertEqual(len(http.get_calls), 1)
        self.assertEqual(len(http.post_calls), 3)
        self.assertTrue(
            all(call["data"]["formeLigjore"] == QKB_SHPK_LEGAL_FORM_FILTER for call in http.post_calls)
        )
        self.assertEqual([call["data"]["dataNga"] for call in http.post_calls], ["02/06/2026", "03/06/2026", "04/06/2026"])
        self.assertEqual(result["search_mode"], RUN_MODE_DAILY_LEGAL_FORM_SHPK)
        self.assertEqual(result["legal_form_filter"], QKB_SHPK_LEGAL_FORM_FILTER)
        self.assertEqual(result["canonical_legal_form_filter"], "SHPK")
        self.assertEqual(result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(result["requested_data_nga"], "2026-06-02")
        self.assertEqual(result["requested_data_ne"], "2026-06-04")
        self.assertEqual(result["successful_day_searches"], 3)
        self.assertEqual(result["failed_day_searches"], 0)
        self.assertEqual(result["total_raw_rows_found"], 53)
        self.assertEqual(result["days_returning_exactly_50_results"], 1)
        self.assertEqual(result["days_returning_exactly_50_shpk_results"], 1)
        self.assertEqual(result["potentially_truncated_days"], ["2026-06-03"])
        self.assertEqual(result["potentially_truncated_shpk_days"], ["2026-06-03"])
        self.assertEqual(result["unique_external_keys"], expected_external_keys)
        self.assertNotIn("all|2026-06-02|2026-06-02", result["unique_external_keys"])

        self.assertEqual([record.external_key for record in structured_records], expected_external_keys)
        self.assertEqual(len(raw_fetches), 3)
        self.assertTrue(
            all(
                raw_fetch.extra_metadata["form_data"]["formeLigjore"] == QKB_SHPK_LEGAL_FORM_FILTER
                for raw_fetch in raw_fetches
            )
        )
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].mode, RUN_MODE_DAILY_LEGAL_FORM_SHPK)
        self.assertEqual(runs[0].status, RUN_STATUS_COMPLETED)

    def test_shpk_universe_resumes_from_failed_day_using_shpk_run_mode(self) -> None:
        first_http = _ShpkFakeHttpClient(
            {
                _window_key(data_nga="02/06/2026", data_ne="02/06/2026"): _record_batch(1, prefix="A"),
                _window_key(data_nga="03/06/2026", data_ne="03/06/2026"): RuntimeError("day 2 failed"),
            }
        )
        second_http = _ShpkFakeHttpClient(
            {
                _window_key(data_nga="03/06/2026", data_ne="03/06/2026"): _record_batch(1, prefix="B"),
                _window_key(data_nga="04/06/2026", data_ne="04/06/2026"): _record_batch(1, prefix="C"),
            }
        )
        first_collector = _TestQkbSearchCollector(first_http)
        second_collector = _TestQkbSearchCollector(second_http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                first_result = first_collector.collect_shpk_universe(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 4),
                )
                failed_run = db.scalar(select(QkbSearchRun))
                assert failed_run is not None
                failed_run_id = failed_run.id

                second_result = second_collector.collect_shpk_universe(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 4),
                )
                runs = db.scalars(select(QkbSearchRun).order_by(QkbSearchRun.id)).all()
                structured_records = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()

        self.assertEqual(first_result["run_status"], RUN_STATUS_FAILED)
        self.assertEqual(first_result["run_current_date"], "2026-06-03")
        self.assertEqual(first_result["search_requests_executed"], 2)
        self.assertEqual(first_result["successful_day_searches"], 1)
        self.assertEqual(first_result["failed_day_searches"], 1)

        self.assertEqual(second_result["run_id"], failed_run_id)
        self.assertEqual(second_result["run_start_behavior"], "resuming_existing")
        self.assertEqual(second_result["resume_from_date"], "2026-06-03")
        self.assertEqual(second_result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(second_result["search_requests_executed"], 2)
        self.assertEqual([call["data"]["dataNga"] for call in second_http.post_calls], ["03/06/2026", "04/06/2026"])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].mode, RUN_MODE_DAILY_LEGAL_FORM_SHPK)
        self.assertEqual(runs[0].status, RUN_STATUS_COMPLETED)
        self.assertEqual(
            [record.external_key for record in structured_records],
            [
                "legal_form:SHPK|2026-06-02|2026-06-02",
                "legal_form:SHPK|2026-06-03|2026-06-03",
                "legal_form:SHPK|2026-06-04|2026-06-04",
            ],
        )

    def test_cli_qkb_shpk_universe_delegates_to_collector(self) -> None:
        runner = CliRunner()
        command_result = {
            "search_mode": RUN_MODE_DAILY_LEGAL_FORM_SHPK,
            "requested_data_nga": "2026-06-02",
            "requested_data_ne": "2026-06-04",
            "unique_external_keys": [],
        }

        with (
            patch("albiz_collector.cli.SessionLocal") as session_local,
            patch("albiz_collector.cli.QkbSearchCollector") as collector_cls,
        ):
            session_local.return_value.__enter__.return_value = object()
            collector_cls.return_value.collect_shpk_universe.return_value = command_result

            result = runner.invoke(
                app,
                [
                    "run",
                    "qkb-shpk-universe",
                    "--data-nga",
                    "2026-06-02",
                    "--data-ne",
                    "2026-06-04",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.stdout)
        collector_cls.return_value.collect_shpk_universe.assert_called_once_with(
            session_local.return_value.__enter__.return_value,
            data_nga=date(2026, 6, 2),
            data_ne=date(2026, 6, 4),
            restart=False,
        )
        self.assertEqual(json.loads(result.stdout), command_result)
        self.assertEqual(QKB_SHPK_EXTERNAL_KEY_PREFIX, "legal_form:SHPK")


if __name__ == "__main__":
    unittest.main()
