from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.db import Base
from albiz_collector.models import NormalizedQkbSearchRow, StructuredRecord
from albiz_collector.profiling.report import profile_qkb_legal_forms
from albiz_collector.qkb_legal_forms import canonicalize_qkb_legal_form
from tests.support import isolated_db_environment


def _seed_qkb_legal_form_rows(db) -> None:
    structured_record = StructuredRecord(
        source_name="qkb_search",
        record_type="qkb_search_snapshot",
        external_key="all|2025-01-01|2025-01-01",
        source_url="https://format.qkb.gov.al/kerko-per-subjekt/",
        content_hash="hash-qkb-legal-forms",
    )
    db.add(structured_record)
    db.flush()

    rows = [
        ("M11111111A", "SHPK"),
        ("M22222222B", "SH.P.K."),
        ("M33333333C", "Shoqëri me përgjegjësi të kufizuar"),
        ("M44444444D", "Person Fizik"),
        ("M55555555E", None),
    ]
    db.add_all(
        [
            NormalizedQkbSearchRow(
                structured_record_id=structured_record.id,
                snapshot_external_key=structured_record.external_key,
                source_name="qkb_search",
                result_ordinal=index,
                business_nipt=business_nipt,
                legal_form=legal_form,
            )
            for index, (business_nipt, legal_form) in enumerate(rows, start=1)
        ]
    )
    db.commit()


class QkbLegalFormProfileTests(unittest.TestCase):
    def test_shpk_variants_canonicalize_to_shpk(self) -> None:
        variants = [
            "SHPK",
            "SH.P.K",
            "SH.P.K.",
            "Shoqeri me pergjegjesi te kufizuar",
            "Shoqëri me përgjegjësi të kufizuar",
        ]

        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(canonicalize_qkb_legal_form(variant), "SHPK")

    def test_unknown_legal_forms_have_deterministic_fallback(self) -> None:
        self.assertEqual(canonicalize_qkb_legal_form(" Person   Fizik "), "PERSON FIZIK")
        self.assertEqual(canonicalize_qkb_legal_form("Person.Fizik"), "PERSON FIZIK")
        self.assertIsNone(canonicalize_qkb_legal_form(None))
        self.assertIsNone(canonicalize_qkb_legal_form("   "))

    def test_profile_qkb_legal_forms_counts_shpk_and_non_shpk(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                _seed_qkb_legal_form_rows(db)
                report = profile_qkb_legal_forms(db)

        raw_counts = {item["raw_legal_form"]: item["count"] for item in report["raw_legal_form_counts"]}
        canonical_counts = {
            item["canonical_legal_form"]: item["count"]
            for item in report["canonical_legal_form_counts"]
        }

        self.assertEqual(report["dataset"], "normalized_qkb_search_rows")
        self.assertFalse(report["network_calls_made"])
        self.assertEqual(report["total_rows"], 5)
        self.assertEqual(report["distinct_business_nipts"], 5)
        self.assertEqual(report["shpk_count"], 3)
        self.assertEqual(report["non_shpk_count"], 2)
        self.assertEqual(report["missing_legal_form_count"], 1)
        self.assertEqual(raw_counts["SHPK"], 1)
        self.assertEqual(raw_counts["SH.P.K."], 1)
        self.assertEqual(raw_counts["Shoqëri me përgjegjësi të kufizuar"], 1)
        self.assertEqual(raw_counts["Person Fizik"], 1)
        self.assertEqual(raw_counts[None], 1)
        self.assertEqual(canonical_counts["SHPK"], 3)
        self.assertEqual(canonical_counts["PERSON FIZIK"], 1)
        self.assertEqual(canonical_counts[None], 1)

    def test_cli_qkb_legal_forms_preview_makes_no_network_calls(self) -> None:
        runner = CliRunner()

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                _seed_qkb_legal_form_rows(db)

            with (
                patch("albiz_collector.cli.SessionLocal", session_factory),
                patch(
                    "albiz_collector.cli.QkbSearchCollector.collect",
                    side_effect=AssertionError("qkb search network call attempted"),
                ) as qkb_search_collect,
                patch(
                    "albiz_collector.cli.QkbDocumentClient.fetch_one",
                    side_effect=AssertionError("qkb document network call attempted"),
                ) as qkb_document_fetch,
                patch(
                    "albiz_collector.cli.ExperimentalQkbNoticesCollector.collect",
                    side_effect=AssertionError("qkb notices network call attempted"),
                ) as qkb_notices_collect,
            ):
                result = runner.invoke(app, ["profile", "qkb-legal-forms"])

        self.assertEqual(result.exit_code, 0, result.stdout)
        qkb_search_collect.assert_not_called()
        qkb_document_fetch.assert_not_called()
        qkb_notices_collect.assert_not_called()

        report = json.loads(result.stdout)
        self.assertFalse(report["network_calls_made"])
        self.assertEqual(report["shpk_count"], 3)
        self.assertEqual(report["non_shpk_count"], 2)


if __name__ == "__main__":
    unittest.main()
