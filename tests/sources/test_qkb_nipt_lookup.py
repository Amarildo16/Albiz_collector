from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.db import Base
from albiz_collector.models import NormalizedQkbSearchRow, RawFetch, StructuredRecord
from albiz_collector.sources.qkb_nipt_lookup import (
    QkbNiptLookupCollector,
    load_qkb_lookup_nipts,
)
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _build_html(records: list[dict[str, str]]) -> bytes:
    payload = json.dumps(records, ensure_ascii=False)
    return f"<html><body><script>var response = {payload};</script></body></html>".encode("utf-8")


def _response(nipt: str, records: list[dict[str, str]], *, status_code: int = 200) -> ResponsePayload:
    content = _build_html(records) if status_code == 200 else b"<html><body>Not found</body></html>"
    return ResponsePayload(
        url="https://format.qkb.gov.al/kerko-per-subjekt/",
        status_code=status_code,
        content_type="text/html",
        content=content,
        text=content.decode("utf-8"),
        cookies=None,
    )


class _FakeHttpClient:
    def __init__(self, responses: dict[str, ResponsePayload | Exception]) -> None:
        self._responses = responses
        self.get_calls: list[str] = []
        self.post_calls: list[dict[str, object]] = []

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> ResponsePayload:
        self.get_calls.append(url)
        content = b"<html><body>QKB search session bootstrap</body></html>"
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
        nipt = request_data.get("nipt", "")
        result = self._responses[nipt]
        if isinstance(result, Exception):
            raise result
        return result


class _TestQkbNiptLookupCollector(QkbNiptLookupCollector):
    def __init__(self, http_client: _FakeHttpClient) -> None:
        super().__init__(sleeper=lambda _: None)
        self._fake_http_client = http_client

    def _http_client(self) -> _FakeHttpClient:
        return self._fake_http_client


class QkbNiptLookupTests(unittest.TestCase):
    def test_input_file_loading_normalizes_and_deduplicates_nipts(self) -> None:
        with isolated_db_environment() as (temp_dir, _, _):
            input_path = temp_dir / "nipts.txt"
            input_path.write_text(" j62903125g \nJ62903125G\n\nK01731001m\n", encoding="utf-8")

            loaded = load_qkb_lookup_nipts(input_path)

        self.assertEqual(loaded, ["J62903125G", "K01731001M"])

    def test_single_nipt_lookup_uses_one_uppercase_request_and_materializes(self) -> None:
        nipt = "J62903125G"
        http = _FakeHttpClient(
            {
                nipt: _response(
                    nipt,
                    [
                        {
                            "nipti": nipt,
                            "emriISubjektit": "Example SHPK",
                            "formaLigjore": "SHPK",
                            "dataERegjistrimit": "28/03/2022",
                        }
                    ],
                )
            }
        )
        collector = _TestQkbNiptLookupCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(db, nipt=" j62903125g ", delay_seconds=0)
                raw_fetch = db.scalar(select(RawFetch))
                structured_record = db.scalar(select(StructuredRecord))
                normalized_row = db.scalar(select(NormalizedQkbSearchRow))

        assert raw_fetch is not None
        assert structured_record is not None
        assert normalized_row is not None
        self.assertEqual([call["data"]["nipt"] for call in http.post_calls], [nipt])
        self.assertEqual(result["requested_nipt"], nipt)
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["found_count"], 1)
        self.assertEqual(result["missing_count"], 0)
        self.assertEqual(result["rows_upserted"], 1)
        self.assertEqual(result["rows_materialized"], 1)
        self.assertEqual(raw_fetch.fetch_kind, "targeted_nipt_search_results_page")
        self.assertEqual(raw_fetch.extra_metadata["requested_nipt"], nipt)
        self.assertEqual(raw_fetch.extra_metadata["collection_mode"], "targeted_nipt_lookup")
        self.assertEqual(structured_record.external_key, f"targeted_nipt:{nipt}|none|none")
        self.assertEqual(structured_record.payload["collection_mode"], "targeted_nipt_lookup")
        self.assertEqual(normalized_row.search_nipt, nipt)
        self.assertEqual(normalized_row.business_nipt, nipt)
        self.assertEqual(normalized_row.snapshot_external_key, structured_record.external_key)

    def test_dry_run_makes_no_network_or_persistence_writes(self) -> None:
        nipt = "J62903125G"
        http = _FakeHttpClient({nipt: _response(nipt, [])})
        collector = _TestQkbNiptLookupCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(db, nipt=nipt, delay_seconds=0, dry_run=True)
                raw_fetches = db.scalars(select(RawFetch)).all()
                structured_records = db.scalars(select(StructuredRecord)).all()
                normalized_rows = db.scalars(select(NormalizedQkbSearchRow)).all()

        self.assertEqual(http.get_calls, [])
        self.assertEqual(http.post_calls, [])
        self.assertEqual(result["selected_nipt_count"], 1)
        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(raw_fetches, [])
        self.assertEqual(structured_records, [])
        self.assertEqual(normalized_rows, [])

    def test_empty_result_is_persisted_as_missing_without_normalized_rows(self) -> None:
        nipt = "J62903125G"
        http = _FakeHttpClient({nipt: _response(nipt, [])})
        collector = _TestQkbNiptLookupCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(db, nipt=nipt, delay_seconds=0)
                raw_fetch = db.scalar(select(RawFetch))
                structured_record = db.scalar(select(StructuredRecord))
                normalized_rows = db.scalars(select(NormalizedQkbSearchRow)).all()

        assert raw_fetch is not None
        assert structured_record is not None
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["rows_materialized"], 0)
        self.assertEqual(raw_fetch.status_code, 200)
        self.assertEqual(structured_record.payload["lookup_outcome"], "missing")
        self.assertEqual(normalized_rows, [])

    def test_http_404_is_persisted_as_missing_without_a_case_fallback(self) -> None:
        nipt = "J62903125G"
        http = _FakeHttpClient({nipt: _response(nipt, [], status_code=404)})
        collector = _TestQkbNiptLookupCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = collector.collect(db, nipt="j62903125g", delay_seconds=0)
                raw_fetch = db.scalar(select(RawFetch))

        assert raw_fetch is not None
        self.assertEqual([call["data"]["nipt"] for call in http.post_calls], [nipt])
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["http_errors"], 0)
        self.assertEqual(raw_fetch.status_code, 404)

    def test_existing_qkb_business_is_skipped_unless_force_is_set(self) -> None:
        nipt = "J62903125G"
        http = _FakeHttpClient({nipt: _response(nipt, [])})
        collector = _TestQkbNiptLookupCollector(http)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="existing|none|none",
                    content_hash="existing-hash",
                )
                db.add(record)
                db.flush()
                db.add(
                    NormalizedQkbSearchRow(
                        structured_record_id=record.id,
                        snapshot_external_key=record.external_key,
                        source_name="qkb_search",
                        result_ordinal=1,
                        business_nipt=nipt,
                    )
                )
                db.commit()

                skipped = collector.collect(db, nipt=nipt, delay_seconds=0)
                forced = collector.collect(db, nipt=nipt, delay_seconds=0, force=True)

        self.assertEqual(skipped["selected_nipt_count"], 0)
        self.assertEqual(skipped["skipped_existing"], 1)
        self.assertEqual(forced["selected_nipt_count"], 1)
        self.assertEqual(len(http.post_calls), 1)

    def test_cli_exposes_and_delegates_targeted_nipt_lookup(self) -> None:
        runner = CliRunner()
        command_result = {"dataset": "qkb_search_by_nipt", "selected_nipt_count": 1}

        with (
            patch("albiz_collector.cli.SessionLocal") as session_local,
            patch("albiz_collector.cli.QkbNiptLookupCollector") as collector_cls,
        ):
            session_local.return_value.__enter__.return_value = object()
            collector_cls.return_value.collect.return_value = command_result
            result = runner.invoke(app, ["run", "qkb-search-by-nipt", "--nipt", "j62903125g", "--dry-run"])

        self.assertEqual(result.exit_code, 0, result.stdout)
        collector_cls.return_value.collect.assert_called_once_with(
            session_local.return_value.__enter__.return_value,
            nipt="j62903125g",
            input_path=None,
            limit=100,
            offset=0,
            delay_seconds=1.0,
            force=False,
            dry_run=True,
        )
        self.assertEqual(json.loads(result.stdout), command_result)

        help_result = runner.invoke(app, ["run", "--help"])
        self.assertEqual(help_result.exit_code, 0, help_result.stdout)
        self.assertIn("qkb-search-by-nipt", ANSI_ESCAPE_RE.sub("", help_result.stdout))


if __name__ == "__main__":
    unittest.main()
