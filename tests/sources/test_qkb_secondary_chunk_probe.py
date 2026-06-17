from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import patch

from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.qkb_legal_forms import QKB_SHPK_LEGAL_FORM_VALUE
from albiz_collector.sources.qkb_search import QkbSearchCollector
from albiz_collector.utils.http import ResponsePayload


def _build_form_html(*, include_secondary_filters: bool = True) -> bytes:
    if not include_secondary_filters:
        return b"<html><body><form><input name='dataNga' /></form></body></html>"

    return b"""
    <html>
      <body>
        <form>
          <select id="qarku" name="qarku">
            <option value="">Qarku</option>
            <option value="tirane">Tirane</option>
            <option value="durres">Durres</option>
          </select>
          <select id="qyteti" name="qyteti">
            <option value="">Qyteti</option>
            <option value="tirane">Tirane</option>
          </select>
        </form>
      </body>
    </html>
    """


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _record_batch(count: int, *, prefix: str) -> list[dict[str, str]]:
    return [{"nipti": f"{prefix}{index:03d}"} for index in range(1, count + 1)]


class _SecondaryProbeFakeHttpClient:
    def __init__(
        self,
        responses: dict[str, list[dict[str, str]] | Exception],
        *,
        include_secondary_filters: bool = True,
    ) -> None:
        self._responses = responses
        self._include_secondary_filters = include_secondary_filters
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_SecondaryProbeFakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> ResponsePayload:
        self.get_calls.append(url)
        content = _build_form_html(include_secondary_filters=self._include_secondary_filters)
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
        if request_data.get("formeLigjore") != QKB_SHPK_LEGAL_FORM_VALUE:
            raise AssertionError(f"Unexpected legal-form filter: {request_data.get('formeLigjore')!r}")

        qarku = request_data.get("qarku", "")
        if qarku not in self._responses:
            raise AssertionError(f"Unexpected qarku probe request: {qarku!r}")

        result = self._responses[qarku]
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


class _SecondaryProbeQkbSearchCollector(QkbSearchCollector):
    def __init__(self, http_client: _SecondaryProbeFakeHttpClient) -> None:
        self._fake_http_client = http_client

    def _http_client(self) -> _SecondaryProbeFakeHttpClient:
        return self._fake_http_client

    def save_raw_fetch(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("secondary probe persisted a raw fetch")

    def upsert_structured_record(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("secondary probe persisted a structured record")


class QkbSecondaryChunkProbeTests(unittest.TestCase):
    def test_probe_uses_qarku_candidates_without_persistence(self) -> None:
        http = _SecondaryProbeFakeHttpClient(
            {
                "": _record_batch(50, prefix="BASE"),
                "tirane": _record_batch(30, prefix="TR"),
                "durres": _record_batch(2, prefix="DR"),
            }
        )
        collector = _SecondaryProbeQkbSearchCollector(http)

        result = collector.probe_secondary_chunks(
            probe_date=date(2026, 5, 29),
            forme_ligjore="SHPK",
        )

        self.assertEqual(len(http.get_calls), 1)
        self.assertEqual(len(http.post_calls), 3)
        self.assertEqual(result["persistence"], "none")
        self.assertEqual(result["date"], "2026-05-29")
        self.assertEqual(result["resolved_legal_form_filter"], QKB_SHPK_LEGAL_FORM_VALUE)
        self.assertEqual(result["baseline_records_found"], 50)
        self.assertTrue(result["baseline_potentially_truncated"])
        self.assertEqual(result["candidate_secondary_filter_field_name"], "qarku")
        self.assertEqual(result["candidate_secondary_filter_values_tested"], 2)
        self.assertEqual(
            result["discovered_secondary_filter_fields"],
            [
                {"field_name": "qarku", "option_count": 2},
                {"field_name": "qyteti", "option_count": 1},
            ],
        )
        self.assertEqual(result["total_rows_across_chunks_before_dedupe"], 32)
        self.assertEqual(result["unique_business_nipt_count_across_chunks"], 32)
        self.assertTrue(result["secondary_chunking_appears_sufficient"])
        self.assertEqual(
            [call["data"]["qarku"] for call in http.post_calls],
            ["", "tirane", "durres"],
        )
        self.assertTrue(
            all(call["data"]["formeLigjore"] == QKB_SHPK_LEGAL_FORM_VALUE for call in http.post_calls)
        )

    def test_probe_marks_insufficient_when_any_secondary_chunk_hits_limit(self) -> None:
        http = _SecondaryProbeFakeHttpClient(
            {
                "": _record_batch(50, prefix="BASE"),
                "tirane": _record_batch(50, prefix="TR"),
                "durres": _record_batch(2, prefix="DR"),
            }
        )
        collector = _SecondaryProbeQkbSearchCollector(http)

        result = collector.probe_secondary_chunks(
            probe_date=date(2026, 5, 29),
            forme_ligjore="SHPK",
        )

        self.assertEqual(result["secondary_chunks_returning_exactly_50_results"], 1)
        self.assertEqual(result["potentially_truncated_secondary_filter_values"], ["tirane"])
        self.assertFalse(result["secondary_chunking_appears_sufficient"])
        tirane_result = result["results"][0]
        self.assertEqual(tirane_result["secondary_filter_field_name"], "qarku")
        self.assertEqual(tirane_result["secondary_filter_value"], "tirane")
        self.assertEqual(tirane_result["records_found"], 50)
        self.assertTrue(tirane_result["potentially_truncated"])

    def test_probe_reports_no_usable_secondary_filters(self) -> None:
        http = _SecondaryProbeFakeHttpClient(
            {"": _record_batch(50, prefix="BASE")},
            include_secondary_filters=False,
        )
        collector = _SecondaryProbeQkbSearchCollector(http)

        result = collector.probe_secondary_chunks(
            probe_date=date(2026, 5, 29),
            forme_ligjore="SHPK",
        )

        self.assertEqual(len(http.post_calls), 1)
        self.assertEqual(result["discovered_secondary_filter_fields"], [])
        self.assertIsNone(result["candidate_secondary_filter_field_name"])
        self.assertEqual(result["candidate_secondary_filter_values_tested"], 0)
        self.assertFalse(result["secondary_chunking_appears_sufficient"])

    def test_cli_probe_delegates_without_database_or_persistence(self) -> None:
        runner = CliRunner()
        probe_result = {
            "probe_type": "qkb_secondary_chunk_probe",
            "date": "2026-05-29",
            "persistence": "none",
            "candidate_secondary_filter_field_name": "qarku",
            "candidate_secondary_filter_values_tested": 2,
            "secondary_chunking_appears_sufficient": True,
            "results": [],
        }

        with (
            patch("albiz_collector.cli.SessionLocal", side_effect=AssertionError("database session opened")),
            patch("albiz_collector.cli.QkbSearchCollector") as collector_cls,
        ):
            collector_cls.return_value.probe_secondary_chunks.return_value = probe_result
            result = runner.invoke(
                app,
                [
                    "experimental",
                    "qkb-secondary-chunk-probe",
                    "--date",
                    "2026-05-29",
                    "--forme-ligjore",
                    "SHPK",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.stdout)
        collector_cls.assert_called_once_with()
        collector_cls.return_value.probe_secondary_chunks.assert_called_once_with(
            probe_date=date(2026, 5, 29),
            forme_ligjore="SHPK",
        )
        self.assertEqual(json.loads(result.stdout), probe_result)


if __name__ == "__main__":
    unittest.main()
