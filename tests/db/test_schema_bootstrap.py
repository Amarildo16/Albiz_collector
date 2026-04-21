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

            table_names = set(inspect(engine).get_table_names())

        self.assertIn("raw_fetches", table_names)
        self.assertIn("structured_records", table_names)

    def test_init_db_cli_reports_bootstrap_contract(self) -> None:
        runner = CliRunner()

        with isolated_db_environment():
            result = runner.invoke(app, ["init-db"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Database schema bootstrapped for current models.", result.stdout)
        self.assertIn("does not apply schema migrations", result.stdout)


if __name__ == "__main__":
    unittest.main()