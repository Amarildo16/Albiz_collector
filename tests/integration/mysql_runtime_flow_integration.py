from __future__ import annotations

import json
import unittest

from sqlalchemy import inspect, select, text

from albiz_collector.db import init_db
from albiz_collector.models import NormalizedQkbSearchRow, RawFetch, StructuredRecord
from albiz_collector.normalization.materialize import materialize_qkb_search
from albiz_collector.sources.base import CollectorBase
from tests.integration.support import (
    alembic_head_revision,
    alembic_stamp_head,
    alembic_upgrade_head,
    mysql_integration_environment,
    require_mysql_integration,
)
from tests.support import fixture_path


class _QkbIntegrationCollector(CollectorBase):
    source_name = "qkb_search"


class MySqlRuntimeFlowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_mysql_integration()

    def test_alembic_upgrade_head_creates_expected_schema_on_mysql(self) -> None:
        with mysql_integration_environment() as ctx:
            alembic_upgrade_head()

            inspector = inspect(ctx.engine)
            table_names = set(inspector.get_table_names())
            raw_fetch_columns = {column["name"] for column in inspector.get_columns("raw_fetches")}
            app_feature_columns = {
                column["name"] for column in inspector.get_columns("app_company_features")
            }
            joined_feature_columns = {
                column["name"] for column in inspector.get_columns("joined_company_features")
            }
            qkb_search_run_columns = {
                column["name"] for column in inspector.get_columns("qkb_search_runs")
            }

        self.assertIn("alembic_version", table_names)
        self.assertIn("raw_fetches", table_names)
        self.assertIn("structured_records", table_names)
        self.assertIn("normalized_qkb_search_rows", table_names)
        self.assertIn("qkb_search_runs", table_names)
        self.assertIn("is_corrupted", raw_fetch_columns)
        self.assertIn("corruption_reason", raw_fetch_columns)
        self.assertIn("active_procurement_count", app_feature_columns)
        self.assertIn("safe_winner_to_budget_ratio_avg", app_feature_columns)
        self.assertIn("purchase_tickets_count", app_feature_columns)
        self.assertIn("source_row_count", joined_feature_columns)
        self.assertIn("active_procurement_count", joined_feature_columns)
        self.assertIn("registration_year", joined_feature_columns)
        self.assertIn("has_activity_text", joined_feature_columns)
        self.assertIn("current_date", qkb_search_run_columns)
        self.assertIn("status", qkb_search_run_columns)

    def test_init_db_then_alembic_stamp_head_adopts_existing_mysql_schema(self) -> None:
        with mysql_integration_environment() as ctx:
            init_db()
            alembic_stamp_head()

            with ctx.engine.begin() as connection:
                version_rows = connection.execute(text("SELECT version_num FROM alembic_version")).all()

        self.assertEqual(len(version_rows), 1)
        self.assertEqual(version_rows[0][0], alembic_head_revision())

    def test_core_row_persistence_and_qkb_normalization_work_on_mysql(self) -> None:
        payload = json.loads(
            fixture_path("normalization", "qkb_search_snapshot_payload.json").read_text(
                encoding="utf-8"
            )
        )

        with mysql_integration_environment() as ctx:
            alembic_upgrade_head()
            collector = _QkbIntegrationCollector()

            with ctx.session_factory() as db:
                raw_fetch = collector.save_raw_fetch(
                    db,
                    url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content=fixture_path("qkb_search", "search-results-with-records.html").read_bytes(),
                    fetch_kind="search_results_page",
                    status_code=200,
                    content_type="text/html",
                    filename="qkb-search-integration.html",
                    extra_metadata={"mode": "fixture"},
                )
                structured_record = StructuredRecord(
                    source_name="qkb_search",
                    record_type="qkb_search_snapshot",
                    external_key="M21528028T|2025-04-01|2026-04-17",
                    title="QKB integration snapshot",
                    source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
                    content_hash="snapshot-hash",
                    payload={**payload, "raw_fetch_id": raw_fetch.id},
                )
                db.add(structured_record)
                db.commit()

                stats = materialize_qkb_search(db)
                saved_raw_fetch = db.get(RawFetch, raw_fetch.id)
                normalized_rows = db.scalars(
                    select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.result_ordinal)
                ).all()

        self.assertIsNotNone(saved_raw_fetch)
        self.assertEqual(stats["snapshots_materialized"], 1)
        self.assertEqual(stats["rows_materialized"], 2)
        self.assertEqual(len(normalized_rows), 2)
        self.assertEqual(normalized_rows[0].raw_fetch_id, saved_raw_fetch.id)
        self.assertEqual(normalized_rows[0].business_nipt, "M21528028T")


if __name__ == "__main__":
    unittest.main()
