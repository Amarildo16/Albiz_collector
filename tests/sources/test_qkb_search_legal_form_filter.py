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
from albiz_collector.qkb_legal_forms import (
    QKB_SHA_LEGAL_FORM_VALUE,
    QKB_SHPK_LEGAL_FORM_VALUE,
    resolve_qkb_legal_form_filter,
)
from albiz_collector.sources.qkb_search import QkbSearchCollector, RUN_STATUS_COMPLETED, RUN_STATUS_FAILED
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _record_batch(count: int, *, prefix: str, legal_form: str = "SHPK") -> list[dict[str, str]]:
    return [{"nipti": f"{prefix}{index:03d}", "formaLigjore": legal_form} for index in range(1, count + 1)]


def _window_key(
    *,
    data_nga: str,
    data_ne: str,
    legal_form: str = QKB_SHPK_LEGAL_FORM_VALUE,
) -> tuple[str, str, str]:
    return (data_nga, data_ne, legal_form)


class _LegalFormFakeHttpClient:
    def __init__(self, responses: dict[tuple[str, str, str], list[dict[str, str]] | Exception]) -> None:
        self._responses = responses
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_LegalFormFakeHttpClient":
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
            raise AssertionError(f"Unexpected legal-form QKB search request: {key!r}")

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
    def __init__(self, http_client: _LegalFormFakeHttpClient) -> None:
        self._fake_http_client = http_client

    def _http_client(self) -> _LegalFormFakeHttpClient:
        return self._fake_http_client


class QkbSearchLegalFormFilterTests(unittest.TestCase):
    def test_legal_form_aliases_resolve_to_qkb_filter_values(self) -> None:
        for alias in ("SHPK", "shpk", "SH.P.K", "SH.P.K."):
            with self.subTest(alias=alias):
                self.assertEqual(resolve_qkb_legal_form_filter(alias), QKB_SHPK_LEGAL_FORM_VALUE)

        self.assertEqual(resolve_qkb_legal_form_filter("Person Fizik"), "Person Fizik")
        self.assertEqual(resolve_qkb_legal_form_filter("SHA"), QKB_SHA_LEGAL_FORM_VALUE)
        self.assertEqual(resolve_qkb_legal_form_filter("Unknown Form"), "Unknown Form")
        self.assertIsNone(resolve_qkb_legal_form_filter("   "))

    def test_filtered_daily_chunks_send_resolved_filter_and_use_distinct_external_keys(self) -> None:
        http = _LegalFormFakeHttpClient(
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
                db.add(
                    StructuredRecord(
                        source_name="qkb_search",
                        record_type="qkb_search_snapshot",
                        external_key="all|2026-06-02|2026-06-02",
                        content_hash="broad-existing",
                    )
                )
                db.commit()

                result = collector.collect(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 4),
                    forme_ligjore="SHPK",
                )
                structured_records = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()
                raw_fetches = db.scalars(select(RawFetch).order_by(RawFetch.id)).all()
                runs = db.scalars(select(QkbSearchRun)).all()

        expected_filtered_keys = [
            "legal_form:SHPK|2026-06-02|2026-06-02",
            "legal_form:SHPK|2026-06-03|2026-06-03",
            "legal_form:SHPK|2026-06-04|2026-06-04",
        ]

        self.assertEqual(len(http.get_calls), 1)
        self.assertEqual(len(http.post_calls), 3)
        self.assertTrue(
            all(call["data"]["formeLigjore"] == QKB_SHPK_LEGAL_FORM_VALUE for call in http.post_calls)
        )
        self.assertEqual([call["data"]["dataNga"] for call in http.post_calls], ["02/06/2026", "03/06/2026", "04/06/2026"])
        self.assertEqual(result["search_mode"], "daily_legal_form:SHPK")
        self.assertEqual(result["legal_form_filter"], QKB_SHPK_LEGAL_FORM_VALUE)
        self.assertEqual(result["canonical_legal_form_filter"], "SHPK")
        self.assertEqual(result["run_status"], RUN_STATUS_COMPLETED)
        self.assertEqual(result["total_raw_rows_found"], 53)
        self.assertEqual(result["days_returning_exactly_50_results"], 1)
        self.assertEqual(result["potentially_truncated_days"], ["2026-06-03"])
        self.assertEqual(result["unique_external_keys"], expected_filtered_keys)

        self.assertIn("all|2026-06-02|2026-06-02", [record.external_key for record in structured_records])
        for external_key in expected_filtered_keys:
            self.assertIn(external_key, [record.external_key for record in structured_records])
        self.assertEqual(len(raw_fetches), 3)
        self.assertTrue(
            all(
                raw_fetch.extra_metadata["form_data"]["formeLigjore"] == QKB_SHPK_LEGAL_FORM_VALUE
                for raw_fetch in raw_fetches
            )
        )
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].mode, "daily_legal_form:SHPK")
        self.assertEqual(runs[0].status, RUN_STATUS_COMPLETED)

    def test_raw_legal_form_value_works_and_keeps_same_canonical_external_key(self) -> None:
        http = _LegalFormFakeHttpClient(
            {
                _window_key(data_nga="02/06/2026", data_ne="02/06/2026"): _record_batch(1, prefix="A"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 2),
                    forme_ligjore=QKB_SHPK_LEGAL_FORM_VALUE,
                )

        self.assertEqual(len(http.post_calls), 1)
        self.assertEqual(http.post_calls[0]["data"]["formeLigjore"], QKB_SHPK_LEGAL_FORM_VALUE)
        self.assertEqual(result["unique_external_keys"], ["legal_form:SHPK|2026-06-02|2026-06-02"])
        self.assertEqual(result["search_mode"], "daily_legal_form:SHPK")

    def test_sha_alias_sends_joint_stock_qkb_value(self) -> None:
        http = _LegalFormFakeHttpClient(
            {
                _window_key(
                    data_nga="02/06/2026",
                    data_ne="02/06/2026",
                    legal_form=QKB_SHA_LEGAL_FORM_VALUE,
                ): _record_batch(1, prefix="SA", legal_form="SHA"),
            }
        )
        collector = _TestQkbSearchCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 2),
                    forme_ligjore="SHA",
                )

        self.assertEqual(http.post_calls[0]["data"]["formeLigjore"], QKB_SHA_LEGAL_FORM_VALUE)
        self.assertEqual(result["canonical_legal_form_filter"], "SHA")
        self.assertEqual(result["unique_external_keys"], ["legal_form:SHA|2026-06-02|2026-06-02"])

    def test_filtered_date_range_resumes_from_failed_day(self) -> None:
        first_http = _LegalFormFakeHttpClient(
            {
                _window_key(data_nga="02/06/2026", data_ne="02/06/2026"): _record_batch(1, prefix="A"),
                _window_key(data_nga="03/06/2026", data_ne="03/06/2026"): RuntimeError("day 2 failed"),
            }
        )
        second_http = _LegalFormFakeHttpClient(
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
                first_result = first_collector.collect(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 4),
                    forme_ligjore="SHPK",
                )
                failed_run = db.scalar(select(QkbSearchRun))
                assert failed_run is not None
                failed_run_id = failed_run.id

                second_result = second_collector.collect(
                    db,
                    data_nga=date(2026, 6, 2),
                    data_ne=date(2026, 6, 4),
                    forme_ligjore="SHPK",
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
        self.assertEqual(runs[0].mode, "daily_legal_form:SHPK")
        self.assertEqual(runs[0].status, RUN_STATUS_COMPLETED)
        self.assertEqual(
            [record.external_key for record in structured_records],
            [
                "legal_form:SHPK|2026-06-02|2026-06-02",
                "legal_form:SHPK|2026-06-03|2026-06-03",
                "legal_form:SHPK|2026-06-04|2026-06-04",
            ],
        )

    def test_cli_help_exposes_forme_ligjore_and_removes_special_shpk_command(self) -> None:
        runner = CliRunner()

        run_help = runner.invoke(app, ["run", "--help"])
        qkb_help = runner.invoke(app, ["run", "qkb-search", "--help"])

        self.assertEqual(run_help.exit_code, 0, run_help.stdout)
        self.assertEqual(qkb_help.exit_code, 0, qkb_help.stdout)
        self.assertIn("qkb-search", run_help.stdout)
        self.assertNotIn("qkb-shpk-registry", run_help.stdout)
        self.assertNotIn("qkb-shpk-universe", run_help.stdout)
        self.assertIn("forme-ligjore", qkb_help.stdout)

    def test_cli_qkb_search_passes_forme_ligjore_to_collector(self) -> None:
        runner = CliRunner()
        command_result = {
            "search_mode": "daily_legal_form:SHPK",
            "requested_data_nga": "2026-06-02",
            "requested_data_ne": "2026-06-04",
            "unique_external_keys": [],
        }

        with (
            patch("albiz_collector.cli.SessionLocal") as session_local,
            patch("albiz_collector.cli.QkbSearchCollector") as collector_cls,
        ):
            session_local.return_value.__enter__.return_value = object()
            collector_cls.return_value.collect.return_value = command_result

            result = runner.invoke(
                app,
                [
                    "run",
                    "qkb-search",
                    "--data-nga",
                    "2026-06-02",
                    "--data-ne",
                    "2026-06-04",
                    "--forme-ligjore",
                    "SHPK",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.stdout)
        collector_cls.return_value.collect.assert_called_once_with(
            session_local.return_value.__enter__.return_value,
            nipt=None,
            data_nga=date(2026, 6, 2),
            data_ne=date(2026, 6, 4),
            forme_ligjore="SHPK",
            restart=False,
        )
        self.assertEqual(json.loads(result.stdout), command_result)


if __name__ == "__main__":
    unittest.main()
