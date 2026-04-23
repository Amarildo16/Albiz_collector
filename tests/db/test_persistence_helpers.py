from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from albiz_collector.db import Base
from albiz_collector.models import RawFetch, StructuredRecord
from albiz_collector.sources.base import CollectorBase
from tests.support import isolated_db_environment


class TestCollector(CollectorBase):
    source_name = "test_source"


class PersistenceHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = TestCollector()

    def test_save_raw_fetch_creates_row_and_assigns_id_before_commit(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_row = self.collector.save_raw_fetch(
                    db,
                    url="https://example.test/export.csv",
                    content=b"col_a,col_b\n1,2\n",
                    fetch_kind="unit_test",
                    status_code=200,
                    content_type="text/csv",
                    extra_metadata={"year": 2026},
                )

                self.assertIsNotNone(raw_row.id)
                self.assertEqual(raw_row.source_name, "test_source")
                self.assertEqual(raw_row.fetch_kind, "unit_test")
                self.assertEqual(raw_row.status_code, 200)
                self.assertEqual(raw_row.content_type, "text/csv")
                self.assertEqual(raw_row.extra_metadata, {"year": 2026})
                self.assertTrue(raw_row.storage_path.endswith(".csv"))

                db.commit()
                persisted_row = db.scalar(select(RawFetch).where(RawFetch.id == raw_row.id))

            self.assertIsNotNone(persisted_row)
            assert persisted_row is not None
            self.assertEqual(persisted_row.content_hash, raw_row.content_hash)

    def test_save_raw_fetch_uses_distinct_paths_for_different_content_with_same_filename(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                first = self.collector.save_raw_fetch(
                    db,
                    url="https://example.test/detail.html",
                    content=b"<html>first</html>",
                    fetch_kind="unit_test",
                    status_code=200,
                    content_type="text/html",
                    filename="detail.html",
                )
                second = self.collector.save_raw_fetch(
                    db,
                    url="https://example.test/detail.html",
                    content=b"<html>second</html>",
                    fetch_kind="unit_test",
                    status_code=200,
                    content_type="text/html",
                    filename="detail.html",
                )

            self.assertNotEqual(first.storage_path, second.storage_path)
            self.assertIn(first.content_hash, Path(first.storage_path).name)
            self.assertIn(second.content_hash, Path(second.storage_path).name)
            self.assertEqual(Path(first.storage_path).read_bytes(), b"<html>first</html>")
            self.assertEqual(Path(second.storage_path).read_bytes(), b"<html>second</html>")

    def test_upsert_structured_record_updates_existing_row_in_place(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                first = self.collector.upsert_structured_record(
                    db,
                    record_type="snapshot",
                    external_key="record-1",
                    title="Initial title",
                    source_url="https://example.test/1",
                    content_hash="hash-1",
                    payload={"version": 1},
                    published_at=datetime(2026, 4, 1, 12, 0, 0),
                    company_name="Example Co",
                    external_id="ABC123",
                )
                db.commit()

                first_seen_at = first.first_seen_at
                first_id = first.id

                second = self.collector.upsert_structured_record(
                    db,
                    record_type="snapshot",
                    external_key="record-1",
                    title="Updated title",
                    source_url="https://example.test/1-updated",
                    content_hash="hash-2",
                    payload={"version": 2},
                    published_at=datetime(2026, 4, 2, 12, 0, 0),
                    company_name="Example Co Updated",
                    external_id="ABC123",
                )
                db.commit()

                rows = db.scalars(select(StructuredRecord)).all()

            self.assertEqual(len(rows), 1)
            self.assertEqual(second.id, first_id)
            self.assertEqual(rows[0].content_hash, "hash-2")
            self.assertEqual(rows[0].payload, {"version": 2})
            self.assertEqual(rows[0].title, "Updated title")
            self.assertEqual(rows[0].source_url, "https://example.test/1-updated")
            self.assertEqual(rows[0].first_seen_at, first_seen_at)
            self.assertGreaterEqual(rows[0].last_seen_at, first_seen_at)

    def test_committed_raw_fetch_survives_later_failure_before_structured_insert(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            raw_id: int | None = None
            try:
                with session_factory() as db:
                    raw_row = self.collector.save_raw_fetch(
                        db,
                        url="https://example.test/detail.html",
                        content=b"<html>saved first</html>",
                        fetch_kind="ordering_test",
                        status_code=200,
                        content_type="text/html",
                        extra_metadata={"phase": "pre-parse"},
                        filename="detail.html",
                    )
                    raw_id = raw_row.id
                    db.commit()

                    raise RuntimeError("simulated downstream parse failure")
            except RuntimeError:
                pass

            with session_factory() as verify_db:
                raw_rows = verify_db.scalars(select(RawFetch)).all()
                structured_rows = verify_db.scalars(select(StructuredRecord)).all()

            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0].id, raw_id)
            self.assertEqual(raw_rows[0].extra_metadata, {"phase": "pre-parse"})
            self.assertEqual(structured_rows, [])


if __name__ == "__main__":
    unittest.main()
