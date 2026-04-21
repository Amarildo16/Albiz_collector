from __future__ import annotations

import unittest
from datetime import date

from albiz_collector.db import Base
from albiz_collector.features.materialize import materialize_all_features
from albiz_collector.models import NormalizedAppExportRow, NormalizedQkbSearchRow, StructuredRecord
from albiz_collector.profiling.report import profile_all_data, profile_feature_data, profile_normalized_data
from tests.support import isolated_db_environment


class ProfileReportsTests(unittest.TestCase):
    def test_profile_normalized_data_reports_counts_missingness_and_join_coverage(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=1,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-app",
                        ),
                        StructuredRecord(
                            id=2,
                            source_name="qkb_search",
                            record_type="qkb_search_snapshot",
                            external_key="M21528028T|2025-01-01|2026-04-17",
                            content_hash="hash-qkb",
                        ),
                    ]
                )
                db.flush()
                db.add_all(
                    [
                        NormalizedAppExportRow(
                            structured_record_id=1,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=1,
                            procurement_reference="REF-1",
                            publication_date=date(2026, 4, 3),
                            procedure_type="Small Value",
                            contract_type="Services",
                            budget_limit_amount=1000,
                            winner_nipt="M21528028T",
                            winner_value_amount=900,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=1,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=2,
                            procurement_reference="REF-2",
                            publication_date=date(2026, 4, 5),
                            procedure_type="Open Local",
                            contract_type="Services",
                            budget_limit_amount=None,
                            winner_nipt=None,
                            winner_value_amount=None,
                        ),
                        NormalizedQkbSearchRow(
                            structured_record_id=2,
                            snapshot_external_key="M21528028T|2025-01-01|2026-04-17",
                            source_name="qkb_search",
                            result_ordinal=1,
                            business_nipt="M21528028T",
                            business_name="Future Block Group",
                            legal_form="SHPK",
                            registration_date=date(2022, 3, 28),
                            subject_status="Aprovuar",
                            city="Tirane",
                            has_red_flags=False,
                        ),
                    ]
                )
                db.commit()

                report = profile_normalized_data(db)

            self.assertEqual(report["row_counts"]["normalized_app_export_rows"], 2)
            self.assertEqual(report["row_counts"]["normalized_qkb_search_rows"], 1)
            self.assertEqual(report["app_summary"]["winner_nipt_coverage"]["present_count"], 1)
            self.assertEqual(report["join_coverage"]["exact_joinable_company_nipts"], 1)
            self.assertEqual(report["join_coverage"]["app_rows_joinable_exact"], 1)
            self.assertEqual(
                report["app_summary"]["important_field_missingness"]["winner_value_amount"]["missing_count"],
                1,
            )

    def test_profile_feature_data_reports_sparsity_and_readiness(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=1,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-app",
                        ),
                        StructuredRecord(
                            id=2,
                            source_name="qkb_search",
                            record_type="qkb_search_snapshot",
                            external_key="M21528028T|2025-01-01|2026-04-17",
                            content_hash="hash-qkb",
                        ),
                    ]
                )
                db.flush()
                db.add(
                    NormalizedAppExportRow(
                        structured_record_id=1,
                        snapshot_external_key="2026",
                        source_name="app_exports",
                        export_year=2026,
                        row_ordinal=1,
                        procurement_reference="REF-1",
                        publication_date=date(2026, 4, 3),
                        procedure_type="Small Value",
                        contract_type="Services",
                        budget_limit_amount=1000,
                        winner_nipt="M21528028T",
                        winner_value_amount=900,
                    )
                )
                db.add(
                    NormalizedQkbSearchRow(
                        structured_record_id=2,
                        snapshot_external_key="M21528028T|2025-01-01|2026-04-17",
                        source_name="qkb_search",
                        result_ordinal=1,
                        business_nipt="M21528028T",
                        business_name="Future Block Group",
                        legal_form="SHPK",
                        registration_date=date(2022, 3, 28),
                        subject_status="Aprovuar",
                        city="Tirane",
                        has_red_flags=False,
                    )
                )
                db.commit()
                materialize_all_features(db)

                report = profile_feature_data(db)

            self.assertEqual(report["row_counts"]["app_company_features"], 1)
            self.assertEqual(report["row_counts"]["qkb_company_features"], 1)
            self.assertEqual(report["row_counts"]["joined_company_features"], 1)
            self.assertEqual(report["readiness"]["joined_company_features"]["status"], "usable_now")

    def test_profile_all_data_surfaces_blockers_when_join_coverage_is_zero(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=1,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-app",
                        ),
                        StructuredRecord(
                            id=2,
                            source_name="qkb_search",
                            record_type="qkb_search_snapshot",
                            external_key="OTHER|2025-01-01|2026-04-17",
                            content_hash="hash-qkb",
                        ),
                    ]
                )
                db.flush()
                db.add(
                    NormalizedAppExportRow(
                        structured_record_id=1,
                        snapshot_external_key="2026",
                        source_name="app_exports",
                        export_year=2026,
                        row_ordinal=1,
                        procurement_reference="REF-1",
                        publication_date=date(2026, 4, 3),
                        procedure_type="Small Value",
                        contract_type="Services",
                        budget_limit_amount=1000,
                        winner_nipt="M21528028T",
                        winner_value_amount=900,
                    )
                )
                db.add(
                    NormalizedQkbSearchRow(
                        structured_record_id=2,
                        snapshot_external_key="OTHER|2025-01-01|2026-04-17",
                        source_name="qkb_search",
                        result_ordinal=1,
                        business_nipt="L12345678A",
                        business_name="Different Company",
                        legal_form="SHPK",
                        registration_date=date(2022, 3, 28),
                        subject_status="Aprovuar",
                    )
                )
                db.commit()
                materialize_all_features(db)

                report = profile_all_data(db)

            self.assertEqual(report["normalized"]["join_coverage"]["exact_joinable_company_nipts"], 0)
            self.assertIn(
                "There are currently no exact APP to QKB company joins in the local dataset.",
                report["analytical_readiness"]["blockers"],
            )
            self.assertIn(
                "Backfill QKB searches for APP winner NIPTs to increase exact join coverage.",
                report["analytical_readiness"]["priority_backfill_actions"],
            )


if __name__ == "__main__":
    unittest.main()