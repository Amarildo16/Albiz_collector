from __future__ import annotations

import json
import unittest
from datetime import date

from sqlalchemy import select

from albiz_collector.db import Base
from albiz_collector.models import RawFetch, StructuredRecord
from albiz_collector.qkb_legal_forms import QKB_SHPK_LEGAL_FORM_VALUE
from albiz_collector.sources.qkb_search import QkbSearchCollector
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


def _build_form_html() -> bytes:
    return b"""
    <html>
      <body>
        <form>
          <select id="qarku" name="qarku">
            <option value="">Qarku</option>
            <option value="tirane">Tirane</option>
            <option value="durres">Durres</option>
          </select>
        </form>
      </body>
    </html>
    """


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _record_batch(count: int, *, prefix: str) -> list[dict[str, str]]:
    return [
        {
            "nipti": f"{prefix}{index:03d}",
            "formaLigjore": "SHPK",
            "dataERegjistrimit": "29/05/2026",
        }
        for index in range(1, count + 1)
    ]


class _QarkuFallbackFakeHttpClient:
    def __init__(self, responses: dict[str, list[dict[str, str]] | Exception]) -> None:
        self._responses = responses
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_QarkuFallbackFakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> ResponsePayload:
        self.get_calls.append(url)
        content = _build_form_html()
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
            raise AssertionError(f"Unexpected legal form: {request_data.get('formeLigjore')!r}")

        qarku = request_data.get("qarku", "")
        if qarku not in self._responses:
            raise AssertionError(f"Unexpected qarku request: {qarku!r}")

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


class _QarkuFallbackCollector(QkbSearchCollector):
    def __init__(self, http_client: _QarkuFallbackFakeHttpClient) -> None:
        self._fake_http_client = http_client

    def _http_client(self) -> _QarkuFallbackFakeHttpClient:
        return self._fake_http_client


class QkbSearchQarkuFallbackTests(unittest.TestCase):
    def test_no_qarku_fallback_when_baseline_is_below_limit(self) -> None:
        http = _QarkuFallbackFakeHttpClient({"": _record_batch(49, prefix="BASE")})
        collector = _QarkuFallbackCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2026, 5, 29),
                    data_ne=date(2026, 5, 29),
                    forme_ligjore="SHPK",
                )
                structured_records = db.scalars(select(StructuredRecord)).all()
                raw_fetches = db.scalars(select(RawFetch)).all()

        self.assertEqual(len(http.post_calls), 1)
        self.assertEqual(http.post_calls[0]["data"]["qarku"], "")
        self.assertEqual(result["secondary_chunking_applied_days"], [])
        self.assertEqual(result["secondary_chunked_days_count"], 0)
        self.assertEqual(result["unique_external_keys"], ["legal_form:SHPK|2026-05-29|2026-05-29"])
        self.assertEqual([record.external_key for record in structured_records], result["unique_external_keys"])
        self.assertEqual(len(raw_fetches), 1)

    def test_qarku_fallback_persists_secondary_snapshots_without_baseline_collision(self) -> None:
        http = _QarkuFallbackFakeHttpClient(
            {
                "": _record_batch(50, prefix="BASE"),
                "tirane": _record_batch(30, prefix="TR"),
                "durres": _record_batch(26, prefix="DR"),
            }
        )
        collector = _QarkuFallbackCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2026, 5, 29),
                    data_ne=date(2026, 5, 29),
                    forme_ligjore="SHPK",
                )
                structured_records = db.scalars(
                    select(StructuredRecord).order_by(StructuredRecord.external_key)
                ).all()
                raw_fetches = db.scalars(select(RawFetch).order_by(RawFetch.id)).all()

        expected_keys = [
            "legal_form:SHPK|qarku:DURRES|2026-05-29|2026-05-29",
            "legal_form:SHPK|qarku:TIRANE|2026-05-29|2026-05-29",
        ]
        self.assertEqual(len(http.post_calls), 3)
        self.assertEqual([call["data"]["qarku"] for call in http.post_calls], ["", "tirane", "durres"])
        self.assertEqual(result["search_requests_executed"], 3)
        self.assertEqual(result["secondary_chunking_applied_days"], ["2026-05-29"])
        self.assertEqual(result["secondary_chunking_field"], "qarku")
        self.assertEqual(result["secondary_chunked_days_count"], 1)
        self.assertEqual(result["secondary_total_rows_before_dedupe"], 56)
        self.assertEqual(result["secondary_unique_nipt_count"], 56)
        self.assertEqual(result["secondary_chunks_returning_exactly_50_results"], 0)
        self.assertEqual(result["secondary_potentially_truncated_days"], [])
        self.assertEqual(result["potentially_truncated_days"], [])
        self.assertEqual(result["unique_external_keys"], expected_keys)
        self.assertEqual([record.external_key for record in structured_records], expected_keys)
        self.assertNotIn("legal_form:SHPK|2026-05-29|2026-05-29", result["unique_external_keys"])
        self.assertEqual(len(raw_fetches), 2)
        self.assertEqual(
            [raw_fetch.extra_metadata["secondary_filters"] for raw_fetch in raw_fetches],
            [{"qarku": "tirane"}, {"qarku": "durres"}],
        )

    def test_qarku_chunk_at_limit_keeps_day_potentially_truncated(self) -> None:
        http = _QarkuFallbackFakeHttpClient(
            {
                "": _record_batch(50, prefix="BASE"),
                "tirane": _record_batch(50, prefix="TR"),
                "durres": _record_batch(1, prefix="DR"),
            }
        )
        collector = _QarkuFallbackCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(
                    db,
                    data_nga=date(2026, 5, 29),
                    data_ne=date(2026, 5, 29),
                    forme_ligjore="SHPK",
                )

        self.assertEqual(result["secondary_chunks_returning_exactly_50_results"], 1)
        self.assertEqual(result["secondary_potentially_truncated_days"], ["2026-05-29"])
        self.assertEqual(result["potentially_truncated_days"], ["2026-05-29"])
        self.assertEqual(
            result["per_day_summaries"][0]["secondary_potentially_truncated_filter_values"],
            ["tirane"],
        )


if __name__ == "__main__":
    unittest.main()
