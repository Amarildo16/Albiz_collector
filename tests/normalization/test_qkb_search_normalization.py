from __future__ import annotations

import json
import unittest

from sqlalchemy import select

from albiz_collector.db import Base
from albiz_collector.models import NormalizedQkbSearchRow, RawFetch, StructuredRecord
from albiz_collector.normalization.materialize import materialize_qkb_search
from albiz_collector.normalization.qkb_search import build_normalized_qkb_search_rows
from albiz_collector.sources.base import CollectorBase
from tests.support import fixture_path, isolated_db_environment


class _QkbTestCollector(CollectorBase):
    source_name = "qkb_search"


class QkbSearchNormalizationTests(unittest.TestCase):
    def test_build_normalized_qkb_search_rows_extracts_core_fields(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        structured_record = StructuredRecord(
            id=202,
            source_name="qkb_search",
            record_type="qkb_search_snapshot",
            external_key="M21528028T|2025-04-01|2026-04-17",
            title="QKB search snapshot M21528028T|2025-04-01|2026-04-17",
            source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
            content_hash="snapshot-hash",
            payload=payload,
        )

        rows = build_normalized_qkb_search_rows(structured_record)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].structured_record_id, 202)
        self.assertEqual(rows[0].search_nipt, "M21528028T")
        self.assertEqual(rows[0].business_nipt, "M21528028T")
        self.assertEqual(rows[0].registration_date.isoformat(), "2022-03-28")
        self.assertEqual(rows[0].subject_status, "Aprovuar")
        self.assertFalse(rows[0].has_red_flags)
        self.assertEqual(rows[1].trade_name, None)
        self.assertEqual(rows[1].business_nipt, "L12345678A")

    def test_materialize_qkb_search_persists_rows_with_provenance(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        collector = _QkbTestCollector()

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content=b"<html>saved</html>",
                    fetch_kind="search_results_page",
                    status_code=200,
                    content_type="text/html",
                    filename="qkb-search-test.html",
                    extra_metadata={"nipt": "M21528028T"},
                )
                structured_record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="M21528028T|2025-04-01|2026-04-17",
                    title="QKB search snapshot M21528028T|2025-04-01|2026-04-17",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content_hash="snapshot-hash",
                    payload={**payload, "raw_fetch_id": raw_fetch.id},
                )
                db.add(structured_record)
                db.commit()

                structured_record_id = structured_record.id
                structured_record_external_key = structured_record.external_key
                raw_fetch_id = raw_fetch.id

                stats = materialize_qkb_search(db)
                normalized_rows = db.scalars(select(NormalizedQkbSearchRow)).all()

            self.assertEqual(stats["snapshots_materialized"], 1)
            self.assertEqual(stats["rows_materialized"], 2)
            self.assertEqual(len(normalized_rows), 2)
            self.assertEqual(normalized_rows[0].structured_record_id, structured_record_id)
            self.assertEqual(normalized_rows[0].snapshot_external_key, structured_record_external_key)
            self.assertEqual(normalized_rows[0].raw_fetch_id, raw_fetch_id)
            self.assertEqual(normalized_rows[0].source_name, "qkb_search")

    def test_materialize_qkb_search_is_safe_to_rerun(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        collector = _QkbTestCollector()

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content=b"<html>saved</html>",
                    fetch_kind="search_results_page",
                    status_code=200,
                    content_type="text/html",
                    filename="qkb-search-test.html",
                    extra_metadata={"nipt": "M21528028T"},
                )
                structured_record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="M21528028T|2025-04-01|2026-04-17",
                    title="QKB search snapshot M21528028T|2025-04-01|2026-04-17",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content_hash="snapshot-hash",
                    payload={**payload, "raw_fetch_id": raw_fetch.id},
                )
                db.add(structured_record)
                db.commit()

                first_stats = materialize_qkb_search(db)
                first_rows = db.scalars(
                    select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.result_ordinal)
                ).all()

                second_stats = materialize_qkb_search(db)
                second_rows = db.scalars(
                    select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.result_ordinal)
                ).all()

            self.assertEqual(first_stats["rows_inserted"], 2)
            self.assertEqual(first_stats["rows_deleted_before_insert"], 0)
            self.assertEqual(second_stats["rows_inserted"], 2)
            self.assertEqual(second_stats["rows_deleted_before_insert"], 2)
            self.assertEqual(len(first_rows), 2)
            self.assertEqual(len(second_rows), 2)
            self.assertEqual(
                [(row.structured_record_id, row.result_ordinal) for row in second_rows],
                [(second_rows[0].structured_record_id, 1), (second_rows[1].structured_record_id, 2)],
            )

    def test_materialize_qkb_search_requires_valid_raw_fetch_provenance(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                structured_record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="M21528028T|2025-04-01|2026-04-17",
                    title="QKB search snapshot M21528028T|2025-04-01|2026-04-17",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content_hash="snapshot-hash",
                    payload={**payload, "raw_fetch_id": 999999},
                )
                db.add(structured_record)
                db.commit()

                stats = materialize_qkb_search(db)
                normalized_rows = db.scalars(select(NormalizedQkbSearchRow)).all()

            self.assertEqual(stats["snapshots_materialized"], 0)
            self.assertEqual(stats["snapshots_failed"], 1)
            self.assertEqual(stats["rows_inserted"], 0)
            self.assertEqual(normalized_rows, [])
            self.assertIn("raw fetch 999999 not found", stats["errors"][0]["error"])

    def test_materialize_qkb_search_skips_corrupted_raw_fetches(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_fetch = RawFetch(
                    source_name="qkb_search",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    fetch_kind="search_results_page",
                    status_code=200,
                    content_type="text/html",
                    content_hash="raw-hash",
                    storage_path="tests/fixtures/qkb_search/search-results-with-records.html",
                    is_corrupted=True,
                    corruption_reason="content_hash mismatch",
                )
                db.add(raw_fetch)
                db.flush()
                db.add(
                    StructuredRecord(
                        source_name="qkb_search",
                        record_type="qkb_search_snapshot",
                        external_key="M21528028T|2025-04-01|2026-04-17",
                        title="QKB search snapshot M21528028T|2025-04-01|2026-04-17",
                        source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                        content_hash="snapshot-hash",
                        payload={**payload, "raw_fetch_id": raw_fetch.id},
                    )
                )
                db.commit()

                stats = materialize_qkb_search(db)
                normalized_rows = db.scalars(select(NormalizedQkbSearchRow)).all()

            self.assertEqual(stats["snapshots_materialized"], 0)
            self.assertEqual(stats["snapshots_failed"], 0)
            self.assertEqual(stats["snapshots_skipped_corrupted"], 1)
            self.assertEqual(normalized_rows, [])
            self.assertIn("marked corrupted: content_hash mismatch", stats["skipped"][0]["reason"])

    def test_materialize_qkb_search_skips_superseded_legal_form_baseline_when_qarku_chunks_exist(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        baseline_payload = {
            **payload,
            "nipt": None,
            "legal_form_filter": "Shoqeri me pergjegjesi te kufizuar",
            "canonical_legal_form_filter": "SHPK",
            "secondary_filters": {},
            "data_nga": "2026-05-29",
            "data_ne": "2026-05-29",
        }
        qarku_payload = {
            **baseline_payload,
            "secondary_filters": {"qarku": "tirane"},
            "secondary_filter_labels": {"qarku": "Tirane"},
            "response": [payload["response"][0]],
        }
        collector = _QkbTestCollector()

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                baseline_raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content=b"<html>baseline</html>",
                    fetch_kind="search_results_page",
                    status_code=200,
                    content_type="text/html",
                    filename="qkb-search-baseline.html",
                    extra_metadata={},
                )
                baseline_record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="legal_form:SHPK|2026-05-29|2026-05-29",
                    title="QKB search snapshot legal_form:SHPK|2026-05-29|2026-05-29",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content_hash="baseline-hash",
                    payload={**baseline_payload, "raw_fetch_id": baseline_raw_fetch.id},
                )
                db.add(baseline_record)
                db.commit()

                first_stats = materialize_qkb_search(db)
                first_rows = db.scalars(select(NormalizedQkbSearchRow)).all()
                baseline_record_id = baseline_record.id
                db.expunge_all()

                qarku_raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content=b"<html>qarku</html>",
                    fetch_kind="search_results_page",
                    status_code=200,
                    content_type="text/html",
                    filename="qkb-search-qarku.html",
                    extra_metadata={},
                )
                qarku_record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="legal_form:SHPK|qarku:TIRANE|2026-05-29|2026-05-29",
                    title="QKB search snapshot legal_form:SHPK|qarku:TIRANE|2026-05-29|2026-05-29",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content_hash="qarku-hash",
                    payload={**qarku_payload, "raw_fetch_id": qarku_raw_fetch.id},
                )
                db.add(qarku_record)
                db.commit()

                second_stats = materialize_qkb_search(db)
                second_rows = db.scalars(
                    select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.snapshot_external_key)
                ).all()

        self.assertEqual(first_stats["snapshots_materialized"], 1)
        self.assertEqual(len(first_rows), 2)
        self.assertEqual(second_stats["snapshots_skipped_superseded"], 1)
        self.assertEqual(second_stats["rows_deleted_before_insert"], 2)
        self.assertEqual(second_stats["rows_inserted"], 1)
        self.assertEqual(len(second_rows), 1)
        self.assertEqual(second_rows[0].snapshot_external_key, "legal_form:SHPK|qarku:TIRANE|2026-05-29|2026-05-29")
        self.assertNotEqual(second_rows[0].structured_record_id, baseline_record_id)
        self.assertIn("superseded by qarku chunk snapshots", second_stats["skipped"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
