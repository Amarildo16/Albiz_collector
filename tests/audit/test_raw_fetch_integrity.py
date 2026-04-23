from __future__ import annotations

import unittest

from sqlalchemy import select

from albiz_collector.audit import inventory_raw_fetch_integrity
from albiz_collector.db import Base
from albiz_collector.models import RawFetch
from albiz_collector.utils.hashing import sha256_bytes
from tests.support import fixture_path, isolated_db_environment


class RawFetchIntegrityTests(unittest.TestCase):
    def test_inventory_reports_content_hash_mismatches_without_mutating_rows(self) -> None:
        fixture = fixture_path("normalization", "app_procurement_rows.csv")

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_row = RawFetch(
                    source_name="app_exports",
                    source_url="https://example.test/export.csv",
                    fetch_kind="unit_test",
                    status_code=200,
                    content_type="text/csv",
                    content_hash="not-the-real-hash",
                    storage_path="tests/fixtures/normalization/app_procurement_rows.csv",
                )
                db.add(raw_row)
                db.commit()
                raw_fetch_id = raw_row.id

                report = inventory_raw_fetch_integrity(db)
                persisted_row = db.scalar(select(RawFetch).where(RawFetch.id == raw_fetch_id))

        self.assertEqual(report["rows_scanned"], 1)
        self.assertEqual(report["issues_found"], 1)
        self.assertEqual(report["content_hash_mismatch_count"], 1)
        self.assertEqual(report["missing_file_count"], 0)
        self.assertEqual(report["issues"][0]["raw_fetch_id"], raw_fetch_id)
        self.assertEqual(report["issues"][0]["issue_type"], "content_hash_mismatch")
        self.assertEqual(report["issues"][0]["resolved_path"], str(fixture.resolve()))
        self.assertIsNotNone(persisted_row)
        assert persisted_row is not None
        self.assertEqual(persisted_row.content_hash, "not-the-real-hash")

    def test_inventory_reports_missing_files_and_limit_truncation(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        RawFetch(
                            source_name="qkb_search",
                            source_url="https://example.test/a",
                            fetch_kind="unit_test",
                            status_code=200,
                            content_type="text/html",
                            content_hash="hash-a",
                            storage_path="data/raw/missing-a.html",
                        ),
                        RawFetch(
                            source_name="qkb_search",
                            source_url="https://example.test/b",
                            fetch_kind="unit_test",
                            status_code=200,
                            content_type="text/html",
                            content_hash="hash-b",
                            storage_path="data/raw/missing-b.html",
                        ),
                    ]
                )
                db.commit()

                report = inventory_raw_fetch_integrity(db, source_name="qkb_search", limit=1)

        self.assertEqual(report["rows_scanned"], 2)
        self.assertEqual(report["issues_found"], 2)
        self.assertEqual(report["missing_file_count"], 2)
        self.assertTrue(report["issues_truncated"])
        self.assertEqual(report["returned_issue_count"], 1)
        self.assertEqual(report["issues"][0]["issue_type"], "missing_file")

    def test_inventory_can_mark_detected_rows_as_corrupted(self) -> None:
        fixture = fixture_path("normalization", "app_procurement_rows.csv")

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_row = RawFetch(
                    source_name="app_exports",
                    source_url="https://example.test/export.csv",
                    fetch_kind="unit_test",
                    status_code=200,
                    content_type="text/csv",
                    content_hash="not-the-real-hash",
                    storage_path="tests/fixtures/normalization/app_procurement_rows.csv",
                )
                db.add(raw_row)
                db.commit()

                report = inventory_raw_fetch_integrity(db, mark_corrupted=True)
                refreshed = db.scalar(select(RawFetch).where(RawFetch.id == raw_row.id))

        self.assertEqual(report["issues_found"], 1)
        self.assertEqual(report["rows_marked_corrupted"], 1)
        self.assertEqual(report["corrupted_rows_after_scan"], 1)
        self.assertEqual(report["issues"][0]["reason"], "content_hash mismatch")
        self.assertEqual(report["issues"][0]["resolved_path"], str(fixture.resolve()))
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertTrue(refreshed.is_corrupted)
        self.assertEqual(refreshed.corruption_reason, "content_hash mismatch")

    def test_inventory_can_list_already_corrupted_rows(self) -> None:
        fixture = fixture_path("normalization", "app_procurement_rows.csv")

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add(
                    RawFetch(
                        source_name="qkb_search",
                        source_url="https://example.test/search",
                        fetch_kind="unit_test",
                        status_code=200,
                        content_type="text/csv",
                        content_hash=sha256_bytes(fixture.read_bytes()),
                        storage_path="tests/fixtures/normalization/app_procurement_rows.csv",
                        is_corrupted=True,
                        corruption_reason="content_hash mismatch",
                    )
                )
                db.commit()

                report = inventory_raw_fetch_integrity(db, corrupted_only=True)

        self.assertEqual(report["issues_found"], 0)
        self.assertEqual(report["corrupted_rows_after_scan"], 1)
        self.assertEqual(report["returned_issue_count"], 1)
        self.assertEqual(report["issues"][0]["issue_type"], "marked_corrupted")
        self.assertTrue(report["issues"][0]["is_corrupted"])


if __name__ == "__main__":
    unittest.main()
