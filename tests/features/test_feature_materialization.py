from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy import select

from albiz_collector.db import Base
from albiz_collector.features.materialize import (
    materialize_all_features,
    materialize_app_features,
    materialize_joined_features,
    materialize_qkb_features,
)
from albiz_collector.features.registry import get_feature_registry
from albiz_collector.models import (
    AppCompanyFeature,
    JoinedCompanyFeature,
    NormalizedAppExportRow,
    NormalizedQkbSearchRow,
    QkbCompanyFeature,
    StructuredRecord,
)
from tests.support import isolated_db_environment


class FeatureMaterializationTests(unittest.TestCase):
    def test_materialize_app_features_builds_exact_nipt_company_aggregates(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=1,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2025",
                            content_hash="hash-1",
                        ),
                        StructuredRecord(
                            id=2,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-2",
                        ),
                    ]
                )
                db.flush()
                db.add_all(
                    [
                        NormalizedAppExportRow(
                            structured_record_id=1,
                            snapshot_external_key="2025",
                            source_name="app_exports",
                            export_year=2025,
                            row_ordinal=1,
                            procurement_reference="REF-1",
                            contracting_authority="Authority A",
                            procedure_type="Small Value",
                            contract_type="Services",
                            publication_date=date(2025, 5, 1),
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=1000,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=800,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=2,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=1,
                            procurement_reference="REF-2",
                            contracting_authority="Authority B",
                            procedure_type="Open Local",
                            contract_type="Works",
                            publication_date=date(2026, 4, 3),
                            is_cancelled=True,
                            is_suspended=False,
                            budget_limit_amount=2000,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=None,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=2,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=2,
                            procurement_reference="REF-3",
                            contracting_authority="Authority B",
                            procedure_type="Open Local",
                            contract_type="Services",
                            publication_date=date(2026, 4, 10),
                            is_cancelled=False,
                            is_suspended=True,
                            budget_limit_amount=1500,
                            winner_name=None,
                            winner_nipt=None,
                            winner_value_amount=None,
                        ),
                    ]
                )
                db.commit()

                stats = materialize_app_features(db)
                features = db.scalars(select(AppCompanyFeature)).all()

            self.assertEqual(stats["rows_materialized"], 1)
            self.assertEqual(stats["groups_skipped"], 1)
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0].company_nipt, "M21528028T")
            self.assertEqual(features[0].source_row_count, 2)
            self.assertEqual(str(features[0].total_budget_limit_amount), "3000.00")
            self.assertEqual(str(features[0].total_winner_value_amount), "800.00")
            self.assertEqual(features[0].cancelled_procurement_count, 1)
            self.assertTrue(features[0].has_small_value_procedures)
            self.assertTrue(features[0].has_open_local_procedures)

    def test_materialize_qkb_features_handles_missing_optional_fields(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add(
                    StructuredRecord(
                        id=10,
                        source_name="qkb_search",
                        record_type="qkb_search_snapshot",
                        external_key="M21528028T|2025-01-01|2026-04-17",
                        content_hash="hash-qkb",
                    )
                )
                db.flush()
                db.add_all(
                    [
                        NormalizedQkbSearchRow(
                            structured_record_id=10,
                            snapshot_external_key="M21528028T|2025-01-01|2026-04-17",
                            source_name="qkb_search",
                            result_ordinal=1,
                            search_nipt="M21528028T",
                            search_date_from=date(2025, 1, 1),
                            search_date_to=date(2026, 4, 17),
                            business_nipt="M21528028T",
                            business_name="Future Block Group",
                            trade_name=None,
                            legal_form="SHPK",
                            registration_date=date(2022, 3, 28),
                            city="Tirane",
                            ownership_text="Shqiptare (100%)",
                            subject_status="Aprovuar",
                            subject_type=None,
                            activity_text="Software",
                            administrators_text=None,
                            has_red_flags=False,
                        ),
                        NormalizedQkbSearchRow(
                            structured_record_id=10,
                            snapshot_external_key="MISSING|2025-01-01|2026-04-17",
                            source_name="qkb_search",
                            result_ordinal=2,
                            search_nipt=None,
                            search_date_from=date(2025, 1, 1),
                            search_date_to=date(2026, 4, 17),
                            business_nipt="L12345678A",
                            business_name="Subjekt Test",
                            trade_name=None,
                            legal_form=None,
                            registration_date=None,
                            city=None,
                            ownership_text=None,
                            subject_status="Aktiv",
                            subject_type=None,
                            activity_text=None,
                            administrators_text=None,
                            has_red_flags=None,
                        ),
                    ]
                )
                db.commit()

                stats = materialize_qkb_features(db)
                features = db.scalars(
                    select(QkbCompanyFeature).order_by(QkbCompanyFeature.company_nipt)
                ).all()

            self.assertEqual(stats["rows_materialized"], 2)
            self.assertEqual(features[0].company_nipt, "L12345678A")
            self.assertEqual(features[0].registration_year, None)
            self.assertFalse(features[0].has_activity_text)
            self.assertEqual(features[1].registration_year, 2022)
            self.assertTrue(features[1].has_activity_text)

    def test_materialize_joined_features_uses_only_exact_nipt_matches(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=20,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-app",
                        ),
                        StructuredRecord(
                            id=21,
                            source_name="qkb_search",
                            record_type="qkb_search_snapshot",
                            external_key="M21528028T|2025-01-01|2026-04-17",
                            content_hash="hash-qkb-1",
                        ),
                        StructuredRecord(
                            id=22,
                            source_name="qkb_search",
                            record_type="qkb_search_snapshot",
                            external_key="NAMEONLY|2025-01-01|2026-04-17",
                            content_hash="hash-qkb-2",
                        ),
                    ]
                )
                db.flush()
                db.add_all(
                    [
                        NormalizedAppExportRow(
                            structured_record_id=20,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=1,
                            procurement_reference="REF-10",
                            contracting_authority="Authority A",
                            procedure_type="Small Value",
                            contract_type="Services",
                            publication_date=date(2026, 4, 3),
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=1000,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=900,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=20,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=2,
                            procurement_reference="REF-11",
                            contracting_authority="Authority A",
                            procedure_type="Open Local",
                            contract_type="Services",
                            publication_date=date(2026, 4, 5),
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=1200,
                            winner_name="Name Only Company",
                            winner_nipt=None,
                            winner_value_amount=1100,
                        ),
                        NormalizedQkbSearchRow(
                            structured_record_id=21,
                            snapshot_external_key="M21528028T|2025-01-01|2026-04-17",
                            source_name="qkb_search",
                            result_ordinal=1,
                            search_nipt="M21528028T",
                            search_date_from=date(2025, 1, 1),
                            search_date_to=date(2026, 4, 17),
                            business_nipt="M21528028T",
                            business_name="Future Block Group",
                            legal_form="SHPK",
                            registration_date=date(2022, 3, 28),
                            city="Tirane",
                            subject_status="Aprovuar",
                            has_red_flags=False,
                        ),
                        NormalizedQkbSearchRow(
                            structured_record_id=22,
                            snapshot_external_key="NAMEONLY|2025-01-01|2026-04-17",
                            source_name="qkb_search",
                            result_ordinal=1,
                            search_nipt=None,
                            search_date_from=date(2025, 1, 1),
                            search_date_to=date(2026, 4, 17),
                            business_nipt=None,
                            business_name="Name Only Company",
                            legal_form="SHPK",
                            registration_date=date(2023, 1, 1),
                            city="Tirane",
                            subject_status="Aktiv",
                            has_red_flags=None,
                        ),
                    ]
                )
                db.commit()

                stats = materialize_joined_features(db)
                features = db.scalars(select(JoinedCompanyFeature)).all()

            self.assertEqual(stats["rows_materialized"], 1)
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0].company_nipt, "M21528028T")
            self.assertTrue(features[0].exact_join_match)
            self.assertEqual(features[0].legal_form, "SHPK")
            self.assertEqual(features[0].company_age_days_at_first_procurement, 1467)

    def test_feature_materialization_is_safe_to_rerun(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=30,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-app",
                        ),
                        StructuredRecord(
                            id=31,
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
                        structured_record_id=30,
                        snapshot_external_key="2026",
                        source_name="app_exports",
                        export_year=2026,
                        row_ordinal=1,
                        procurement_reference="REF-20",
                        contracting_authority="Authority A",
                        procedure_type="Small Value",
                        contract_type="Services",
                        publication_date=date(2026, 4, 3),
                        is_cancelled=False,
                        is_suspended=False,
                        budget_limit_amount=1000,
                        winner_name="Future Block Group",
                        winner_nipt="M21528028T",
                        winner_value_amount=900,
                    )
                )
                db.add(
                    NormalizedQkbSearchRow(
                        structured_record_id=31,
                        snapshot_external_key="M21528028T|2025-01-01|2026-04-17",
                        source_name="qkb_search",
                        result_ordinal=1,
                        search_nipt="M21528028T",
                        search_date_from=date(2025, 1, 1),
                        search_date_to=date(2026, 4, 17),
                        business_nipt="M21528028T",
                        business_name="Future Block Group",
                        legal_form="SHPK",
                        registration_date=date(2022, 3, 28),
                        city="Tirane",
                        subject_status="Aprovuar",
                        has_red_flags=False,
                    )
                )
                db.commit()

                first_stats = materialize_all_features(db)
                second_stats = materialize_all_features(db)
                app_features = db.scalars(select(AppCompanyFeature)).all()
                qkb_features = db.scalars(select(QkbCompanyFeature)).all()
                joined_features = db.scalars(select(JoinedCompanyFeature)).all()

            self.assertEqual(first_stats["app"]["rows_inserted"], 1)
            self.assertEqual(second_stats["app"]["rows_deleted_before_insert"], 1)
            self.assertEqual(second_stats["qkb"]["rows_deleted_before_insert"], 1)
            self.assertEqual(second_stats["joined"]["rows_deleted_before_insert"], 1)
            self.assertEqual(len(app_features), 1)
            self.assertEqual(len(qkb_features), 1)
            self.assertEqual(len(joined_features), 1)

    def test_feature_registry_exposes_confidence_boundaries(self) -> None:
        registry = get_feature_registry()

        self.assertIn("app_company_features", registry)
        self.assertEqual(registry["joined_company_features"][0].confidence, "safe")


if __name__ == "__main__":
    unittest.main()