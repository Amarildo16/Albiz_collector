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


if __name__ == "__main__":
    unittest.main()