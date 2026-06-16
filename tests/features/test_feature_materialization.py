from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy import inspect, select

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
    RawFetch,
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
            self.assertEqual(features[0].active_procurement_count, 1)
            self.assertEqual(str(features[0].total_budget_limit_amount), "3000.00")
            self.assertEqual(str(features[0].total_winner_value_amount), "800.00")
            self.assertEqual(str(features[0].active_total_budget_limit_amount), "1000.00")
            self.assertEqual(str(features[0].active_total_winner_value_amount), "800.00")
            self.assertEqual(str(features[0].cancelled_total_budget_limit_amount), "2000.00")
            self.assertIsNone(features[0].cancelled_total_winner_value_amount)
            self.assertEqual(features[0].cancelled_procurement_count, 1)
            self.assertEqual(str(features[0].cancelled_procurement_rate), "0.5000")
            self.assertTrue(features[0].has_small_value_procedures)
            self.assertTrue(features[0].has_open_local_procedures)

    def test_materialize_app_features_builds_enhanced_company_features(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            app_feature_columns = {column["name"] for column in inspect(engine).get_columns("app_company_features")}
            for column_name in {
                "source_row_count",
                "total_budget_limit_amount",
                "has_small_value_procedures",
                "active_procurement_count",
                "safe_winner_to_budget_ratio_avg",
                "purchase_tickets_count",
                "rows_with_valid_ratio_count",
            }:
                self.assertIn(column_name, app_feature_columns)

            with session_factory() as db:
                db.add(
                    StructuredRecord(
                        id=3,
                        source_name="app_exports",
                        record_type="procurement_export_year",
                        external_key="2026",
                        content_hash="hash-3",
                    )
                )
                db.flush()
                db.add_all(
                    [
                        NormalizedAppExportRow(
                            structured_record_id=3,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=1,
                            procurement_reference="REF-A",
                            contracting_authority="Authority A",
                            procedure_type="Small Value",
                            contract_type="Services",
                            publication_date=date(2020, 1, 10),
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=100,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=50,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=3,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2010,
                            row_ordinal=2,
                            procurement_reference="REF-B",
                            contracting_authority="Authority B",
                            procedure_type="Open Local",
                            contract_type="Works",
                            publication_date=date(2022, 3, 1),
                            is_cancelled=True,
                            is_suspended=True,
                            budget_limit_amount=200,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=150,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=3,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=3,
                            procurement_reference="REF-C",
                            contracting_authority="Authority A",
                            procedure_type="Purchase Tickets",
                            contract_type="Services",
                            publication_date=date(2021, 6, 1),
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=0,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=75,
                        ),
                        NormalizedAppExportRow(
                            structured_record_id=3,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=4,
                            procurement_reference="REF-D",
                            contracting_authority="Authority C",
                            procedure_type="Purchase Tickets",
                            contract_type="Services",
                            publication_date=None,
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=None,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=25,
                        ),
                    ]
                )
                db.commit()

                stats = materialize_app_features(db)
                feature = db.scalars(select(AppCompanyFeature)).one()

            self.assertEqual(stats["rows_materialized"], 1)
            self.assertEqual(feature.source_row_count, 4)
            self.assertEqual(feature.active_procurement_count, 3)
            self.assertEqual(feature.cancelled_procurement_count, 1)
            self.assertEqual(feature.suspended_procurement_count, 1)
            self.assertEqual(str(feature.cancelled_procurement_rate), "0.2500")
            self.assertEqual(str(feature.suspended_procurement_rate), "0.2500")
            self.assertEqual(str(feature.total_budget_limit_amount), "300.00")
            self.assertEqual(str(feature.total_winner_value_amount), "300.00")
            self.assertEqual(str(feature.active_total_budget_limit_amount), "100.00")
            self.assertEqual(str(feature.active_total_winner_value_amount), "150.00")
            self.assertEqual(str(feature.cancelled_total_budget_limit_amount), "200.00")
            self.assertEqual(str(feature.cancelled_total_winner_value_amount), "150.00")
            self.assertEqual(str(feature.safe_winner_to_budget_ratio_avg), "0.625000")
            self.assertEqual(str(feature.safe_winner_to_budget_ratio_min), "0.500000")
            self.assertEqual(str(feature.safe_winner_to_budget_ratio_max), "0.750000")
            self.assertEqual(feature.purchase_tickets_count, 2)
            self.assertEqual(str(feature.purchase_tickets_total_winner_value), "100.00")
            self.assertEqual(feature.zero_budget_with_winner_value_count, 1)
            self.assertEqual(str(feature.zero_budget_with_winner_value_rate), "0.2500")
            self.assertEqual(feature.first_procurement_date, date(2020, 1, 10))
            self.assertEqual(feature.last_procurement_date, date(2022, 3, 1))
            self.assertEqual(feature.first_procurement_year, 2020)
            self.assertEqual(feature.last_procurement_year, 2022)
            self.assertEqual(feature.active_year_span, 3)
            self.assertEqual(feature.distinct_contracting_authority_count, 3)
            self.assertEqual(feature.distinct_procedure_type_count, 3)
            self.assertEqual(feature.distinct_contract_type_count, 2)
            self.assertEqual(feature.rows_with_winner_value_count, 4)
            self.assertEqual(feature.rows_with_budget_count, 3)
            self.assertEqual(feature.rows_with_valid_ratio_count, 2)

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

    def test_feature_materialization_ignores_rows_from_corrupted_raw_fetches(self) -> None:
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                db.add_all(
                    [
                        StructuredRecord(
                            id=40,
                            source_name="app_exports",
                            record_type="procurement_export_year",
                            external_key="2026",
                            content_hash="hash-app",
                        ),
                        StructuredRecord(
                            id=41,
                            source_name="qkb_search",
                            record_type="qkb_search_snapshot",
                            external_key="M21528028T|2025-01-01|2026-04-17",
                            content_hash="hash-qkb",
                        ),
                        RawFetch(
                            id=100,
                            source_name="app_exports",
                            source_url="https://example.test/app.csv",
                            fetch_kind="year_export",
                            status_code=200,
                            content_type="text/csv",
                            content_hash="healthy-app",
                            storage_path="tests/fixtures/normalization/app_procurement_rows.csv",
                            is_corrupted=False,
                        ),
                        RawFetch(
                            id=101,
                            source_name="app_exports",
                            source_url="https://example.test/app-corrupt.csv",
                            fetch_kind="year_export",
                            status_code=200,
                            content_type="text/csv",
                            content_hash="corrupt-app",
                            storage_path="tests/fixtures/normalization/app_procurement_rows.csv",
                            is_corrupted=True,
                            corruption_reason="content_hash mismatch",
                        ),
                        RawFetch(
                            id=102,
                            source_name="qkb_search",
                            source_url="https://example.test/qkb.html",
                            fetch_kind="search_results_page",
                            status_code=200,
                            content_type="text/html",
                            content_hash="healthy-qkb",
                            storage_path="tests/fixtures/qkb_search/search-results-with-records.html",
                            is_corrupted=False,
                        ),
                        RawFetch(
                            id=103,
                            source_name="qkb_search",
                            source_url="https://example.test/qkb-corrupt.html",
                            fetch_kind="search_results_page",
                            status_code=200,
                            content_type="text/html",
                            content_hash="corrupt-qkb",
                            storage_path="tests/fixtures/qkb_search/search-results-with-records.html",
                            is_corrupted=True,
                            corruption_reason="content_hash mismatch",
                        ),
                    ]
                )
                db.flush()
                db.add_all(
                    [
                        NormalizedAppExportRow(
                            structured_record_id=40,
                            raw_fetch_id=100,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=1,
                            procurement_reference="REF-30",
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
                            structured_record_id=40,
                            raw_fetch_id=101,
                            snapshot_external_key="2026",
                            source_name="app_exports",
                            export_year=2026,
                            row_ordinal=2,
                            procurement_reference="REF-31",
                            contracting_authority="Authority A",
                            procedure_type="Open Local",
                            contract_type="Services",
                            publication_date=date(2026, 4, 4),
                            is_cancelled=False,
                            is_suspended=False,
                            budget_limit_amount=1100,
                            winner_name="Future Block Group",
                            winner_nipt="M21528028T",
                            winner_value_amount=950,
                        ),
                        NormalizedQkbSearchRow(
                            structured_record_id=41,
                            raw_fetch_id=102,
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
                            structured_record_id=41,
                            raw_fetch_id=103,
                            snapshot_external_key="M21528028T|2025-01-01|2026-04-17",
                            source_name="qkb_search",
                            result_ordinal=2,
                            search_nipt="M21528028T",
                            search_date_from=date(2025, 1, 1),
                            search_date_to=date(2026, 4, 17),
                            business_nipt="M21528028T",
                            business_name="Future Block Group Corrupted",
                            legal_form="SHPK",
                            registration_date=date(2022, 3, 28),
                            city="Tirane",
                            subject_status="Aprovuar",
                            has_red_flags=True,
                        ),
                    ]
                )
                db.commit()

                stats = materialize_all_features(db)
                app_features = db.scalars(select(AppCompanyFeature)).all()
                qkb_features = db.scalars(select(QkbCompanyFeature)).all()
                joined_features = db.scalars(select(JoinedCompanyFeature)).all()

            self.assertEqual(stats["app"]["source_rows_seen"], 1)
            self.assertEqual(stats["qkb"]["source_rows_seen"], 1)
            self.assertEqual(app_features[0].source_row_count, 1)
            self.assertEqual(qkb_features[0].source_row_count, 1)
            self.assertEqual(len(joined_features), 1)
            self.assertFalse(joined_features[0].has_red_flags)

    def test_feature_registry_exposes_confidence_boundaries(self) -> None:
        registry = get_feature_registry()

        self.assertIn("app_company_features", registry)
        app_features = {feature.name: feature for feature in registry["app_company_features"]}
        self.assertEqual(app_features["active_procurement_count"].confidence, "safe")
        self.assertEqual(app_features["safe_winner_to_budget_ratio_avg"].confidence, "caution")
        self.assertEqual(app_features["purchase_tickets_count"].confidence, "caution")
        self.assertIn("rows_with_valid_ratio_count", app_features)
        self.assertEqual(registry["joined_company_features"][0].confidence, "safe")


if __name__ == "__main__":
    unittest.main()
