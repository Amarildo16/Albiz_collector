from __future__ import annotations

import unittest

from sqlalchemy import inspect
from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.db import init_db
from tests.support import isolated_db_environment


class SchemaBootstrapTests(unittest.TestCase):
    def test_init_db_creates_expected_tables_and_is_idempotent(self) -> None:
        with isolated_db_environment() as (_, _, engine):
            init_db()
            init_db()

            inspector = inspect(engine)
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
            opencorporates_profile_columns = {
                column["name"] for column in inspector.get_columns("opencorporates_company_profiles")
            }
            opencorporates_financial_year_columns = {
                column["name"] for column in inspector.get_columns("opencorporates_financial_years")
            }

        self.assertIn("raw_fetches", table_names)
        self.assertIn("structured_records", table_names)
        self.assertIn("qkb_search_runs", table_names)
        self.assertIn("opencorporates_company_profiles", table_names)
        self.assertIn("opencorporates_financial_years", table_names)
        self.assertIn("is_corrupted", raw_fetch_columns)
        self.assertIn("corruption_reason", raw_fetch_columns)
        self.assertIn("active_procurement_count", app_feature_columns)
        self.assertIn("safe_winner_to_budget_ratio_avg", app_feature_columns)
        self.assertIn("purchase_tickets_count", app_feature_columns)
        self.assertIn("authority_hhi", app_feature_columns)
        self.assertIn("max_yoy_value_growth_ratio", app_feature_columns)
        self.assertIn("source_row_count", joined_feature_columns)
        self.assertIn("active_procurement_count", joined_feature_columns)
        self.assertIn("registration_year", joined_feature_columns)
        self.assertIn("has_activity_text", joined_feature_columns)
        self.assertIn("current_date", qkb_search_run_columns)
        self.assertIn("status", qkb_search_run_columns)
        self.assertIn("parse_status", opencorporates_profile_columns)
        self.assertIn("last_fetched_at", opencorporates_profile_columns)
        self.assertIn("revenue_amount", opencorporates_financial_year_columns)
        self.assertIn("profit_before_tax_amount", opencorporates_financial_year_columns)

    def test_init_db_cli_reports_bootstrap_contract(self) -> None:
        runner = CliRunner()

        with isolated_db_environment():
            result = runner.invoke(app, ["init-db"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Database schema bootstrapped for current models.", result.stdout)
        self.assertIn("does not apply schema migrations", result.stdout)
        self.assertIn("Prefer Alembic", result.stdout)


if __name__ == "__main__":
    unittest.main()
