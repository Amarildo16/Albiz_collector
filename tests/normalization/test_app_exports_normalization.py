from __future__ import annotations

import json
import unittest

from sqlalchemy import select

from albiz_collector.db import Base
from albiz_collector.models import NormalizedAppExportRow, RawFetch, StructuredRecord
from albiz_collector.normalization.app_exports import build_normalized_app_export_rows
from albiz_collector.normalization.materialize import materialize_app_exports
from albiz_collector.sources.base import CollectorBase
from tests.support import fixture_path, isolated_db_environment


class _AppTestCollector(CollectorBase):
    source_name = "app_exports"


class AppExportsNormalizationTests(unittest.TestCase):
    def test_build_normalized_app_export_rows_extracts_core_fields(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "app_exports_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        csv_content = fixture_path("normalization", "app_procurement_rows.csv").read_bytes()
        structured_record = StructuredRecord(
            id=101,
            source_name="app_exports",
            record_type="procurement_export_year",
            external_key="2026",
            title="APP procurement export 2026",
            source_url="https://www.app.gov.al/GetData/ExportDocument?year=2026",
            content_hash="snapshot-hash",
            payload=payload,
        )
        raw_fetch = RawFetch(
            id=501,
            source_name="app_exports",
            source_url="https://www.app.gov.al/GetData/ExportDocument?year=2026",
            fetch_kind="year_export",
            status_code=200,
            content_type="text/csv",
            content_hash="raw-hash",
            storage_path="tests/fixtures/normalization/app_procurement_rows.csv",
        )

        rows = build_normalized_app_export_rows(structured_record, raw_fetch, csv_content)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].structured_record_id, 101)
        self.assertEqual(rows[0].raw_fetch_id, 501)
        self.assertEqual(rows[0].export_year, 2026)
        self.assertEqual(rows[0].procurement_reference, "REF-80916-04-03-2026")
        self.assertEqual(rows[0].winner_nipt, "L47230701F")
        self.assertEqual(rows[0].publication_date.isoformat(), "2026-04-03")
        self.assertEqual(str(rows[0].budget_limit_amount), "1000.00")
        self.assertFalse(rows[0].is_cancelled)
        self.assertEqual(rows[1].winner_name, None)
        self.assertEqual(rows[1].source_payload["Objekti_i_prokurimit"], "Sherbim transporti")

    def test_materialize_app_exports_persists_rows_with_provenance(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "app_exports_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        csv_content = fixture_path("normalization", "app_procurement_rows.csv").read_bytes()
        collector = _AppTestCollector()

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://www.app.gov.al/GetData/ExportDocument?year=2026",
                    content=csv_content,
                    fetch_kind="year_export",
                    status_code=200,
                    content_type="text/csv",
                    filename="app_procurement_2026.csv",
                    extra_metadata={"year": 2026},
                )
                structured_record = StructuredRecord(
                    source_name="app_exports",
                    record_type="procurement_export_year",
                    external_key="2026",
                    title="APP procurement export 2026",
                    source_url=raw_fetch.source_url,
                    content_hash="snapshot-hash",
                    payload={**payload, "raw_fetch_id": raw_fetch.id},
                )
                db.add(structured_record)
                db.commit()

                raw_fetch_id = raw_fetch.id
                structured_record_id = structured_record.id

                stats = materialize_app_exports(db)
                normalized_rows = db.scalars(select(NormalizedAppExportRow)).all()

            self.assertEqual(stats["snapshots_materialized"], 1)
            self.assertEqual(stats["rows_materialized"], 2)
            self.assertEqual(len(normalized_rows), 2)
            self.assertEqual(normalized_rows[0].structured_record_id, structured_record_id)
            self.assertEqual(normalized_rows[0].raw_fetch_id, raw_fetch_id)
            self.assertEqual(normalized_rows[0].source_name, "app_exports")
            self.assertEqual(normalized_rows[0].snapshot_external_key, "2026")

    def test_materialize_app_exports_is_safe_to_rerun(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "app_exports_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )
        csv_content = fixture_path("normalization", "app_procurement_rows.csv").read_bytes()
        collector = _AppTestCollector()

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://www.app.gov.al/GetData/ExportDocument?year=2026",
                    content=csv_content,
                    fetch_kind="year_export",
                    status_code=200,
                    content_type="text/csv",
                    filename="app_procurement_2026.csv",
                    extra_metadata={"year": 2026},
                )
                structured_record = StructuredRecord(
                    source_name="app_exports",
                    record_type="procurement_export_year",
                    external_key="2026",
                    title="APP procurement export 2026",
                    source_url=raw_fetch.source_url,
                    content_hash="snapshot-hash",
                    payload={**payload, "raw_fetch_id": raw_fetch.id},
                )
                db.add(structured_record)
                db.commit()

                first_stats = materialize_app_exports(db)
                first_rows = db.scalars(
                    select(NormalizedAppExportRow).order_by(NormalizedAppExportRow.row_ordinal)
                ).all()

                second_stats = materialize_app_exports(db)
                second_rows = db.scalars(
                    select(NormalizedAppExportRow).order_by(NormalizedAppExportRow.row_ordinal)
                ).all()

            self.assertEqual(first_stats["rows_inserted"], 2)
            self.assertEqual(first_stats["rows_deleted_before_insert"], 0)
            self.assertEqual(second_stats["rows_inserted"], 2)
            self.assertEqual(second_stats["rows_deleted_before_insert"], 2)
            self.assertEqual(len(first_rows), 2)
            self.assertEqual(len(second_rows), 2)
            self.assertEqual(
                [(row.structured_record_id, row.row_ordinal) for row in second_rows],
                [(second_rows[0].structured_record_id, 1), (second_rows[1].structured_record_id, 2)],
            )


if __name__ == "__main__":
    unittest.main()