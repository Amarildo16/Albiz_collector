from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import patch

from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.sources.qkb_search import QkbSearchCollector
from albiz_collector.utils.http import ResponsePayload


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _record_batch(count: int, *, prefix: str) -> list[dict[str, str]]:
    return [{"nipti": f"{prefix}{index:03d}"} for index in range(1, count + 1)]


class _ProbeFakeHttpClient:
    def __init__(self, responses: dict[str, list[dict[str, str]] | Exception]) -> None:
        self._responses = responses
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_ProbeFakeHttpClient":
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
        legal_form = request_data.get("formeLigjore", "")
        if legal_form not in self._responses:
            raise AssertionError(f"Unexpected legal-form probe request: {legal_form!r}")

        result = self._responses[legal_form]
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


class _ProbeQkbSearchCollector(QkbSearchCollector):
    def __init__(self, http_client: _ProbeFakeHttpClient) -> None:
        self._fake_http_client = http_client

    def _http_client(self) -> _ProbeFakeHttpClient:
        return self._fake_http_client


class QkbLegalFormChunkProbeTests(unittest.TestCase):
    def test_probe_makes_one_request_per_legal_form_filter_and_marks_truncation(self) -> None:
        legal_form_filters = (
            "Person Fizik",
            "Shoqeri me pergjegjesi te kufizuar",
        )
        http = _ProbeFakeHttpClient(
            {
                "Person Fizik": _record_batch(49, prefix="PF"),
                "Shoqeri me pergjegjesi te kufizuar": _record_batch(50, prefix="SH"),
            }
        )
        collector = _ProbeQkbSearchCollector(http)

        result = collector.probe_legal_form_chunks(
            probe_date=date(2026, 6, 2),
            legal_form_filters=legal_form_filters,
        )

        self.assertEqual(len(http.get_calls), 1)
        self.assertEqual(len(http.post_calls), 2)
        self.assertEqual(
            [call["data"]["formeLigjore"] for call in http.post_calls],
            list(legal_form_filters),
        )
        self.assertEqual(
            [call["data"]["dataNga"] for call in http.post_calls],
            ["02/06/2026", "02/06/2026"],
        )
        self.assertEqual(
            [call["data"]["dataNe"] for call in http.post_calls],
            ["02/06/2026", "02/06/2026"],
        )

        self.assertEqual(result["persistence"], "none")
        self.assertEqual(result["probe_date"], "2026-06-02")
        self.assertEqual(result["total_requests_executed"], 2)
        self.assertEqual(result["total_raw_rows_found"], 99)
        self.assertEqual(result["legal_forms_returning_exactly_50_results"], 1)
        self.assertEqual(
            result["potentially_truncated_legal_forms"],
            ["Shoqeri me pergjegjesi te kufizuar"],
        )
        self.assertFalse(result["legal_form_chunking_appears_sufficient"])

        person_fizik_result = result["results"][0]
        shpk_result = result["results"][1]
        self.assertEqual(person_fizik_result["records_found"], 49)
        self.assertFalse(person_fizik_result["potentially_truncated"])
        self.assertEqual(person_fizik_result["status_code"], 200)
        self.assertEqual(shpk_result["canonical_legal_form"], "SHPK")
        self.assertEqual(shpk_result["records_found"], 50)
        self.assertTrue(shpk_result["potentially_truncated"])
        self.assertEqual(shpk_result["status_code"], 200)

    def test_probe_reports_sufficient_when_all_legal_form_chunks_are_below_limit(self) -> None:
        legal_form_filters = (
            "Person Fizik",
            "Shoqeri aksionare",
        )
        http = _ProbeFakeHttpClient(
            {
                "Person Fizik": _record_batch(2, prefix="PF"),
                "Shoqeri aksionare": _record_batch(1, prefix="SA"),
            }
        )
        collector = _ProbeQkbSearchCollector(http)

        result = collector.probe_legal_form_chunks(
            probe_date=date(2026, 6, 2),
            legal_form_filters=legal_form_filters,
        )

        self.assertEqual(result["total_requests_executed"], 2)
        self.assertEqual(result["total_raw_rows_found"], 3)
        self.assertEqual(result["legal_forms_returning_exactly_50_results"], 0)
        self.assertEqual(result["potentially_truncated_legal_forms"], [])
        self.assertTrue(result["legal_form_chunking_appears_sufficient"])
        self.assertTrue(all(not item["potentially_truncated"] for item in result["results"]))

    def test_cli_probe_delegates_without_database_or_app_collection(self) -> None:
        runner = CliRunner()
        probe_result = {
            "probe_type": "qkb_legal_form_chunk_probe",
            "probe_date": "2026-06-02",
            "persistence": "none",
            "total_requests_executed": 2,
            "total_raw_rows_found": 99,
            "legal_forms_returning_exactly_50_results": 1,
            "legal_form_chunking_appears_sufficient": False,
            "results": [],
        }

        with (
            patch("albiz_collector.cli.SessionLocal", side_effect=AssertionError("database session opened")),
            patch("albiz_collector.cli.AppExportsCollector.collect", side_effect=AssertionError("APP collection invoked")) as app_collect,
            patch("albiz_collector.cli.QkbSearchCollector") as collector_cls,
        ):
            collector_cls.return_value.probe_legal_form_chunks.return_value = probe_result
            result = runner.invoke(
                app,
                ["experimental", "qkb-legal-form-chunk-probe", "--date", "2026-06-02"],
            )

        self.assertEqual(result.exit_code, 0, result.stdout)
        collector_cls.assert_called_once_with()
        collector_cls.return_value.probe_legal_form_chunks.assert_called_once_with(
            probe_date=date(2026, 6, 2),
        )
        app_collect.assert_not_called()
        self.assertEqual(json.loads(result.stdout), probe_result)


if __name__ == "__main__":
    unittest.main()
