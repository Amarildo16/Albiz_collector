from __future__ import annotations

import unittest

from albiz_collector.smoke.source_contracts import (
    SmokeCheckFailure,
    evaluate_app_source_contract,
    evaluate_qkb_search_source_contract,
)
from tests.support import fixture_path


class SourceContractSmokeEvaluationTests(unittest.TestCase):
    def test_evaluate_app_source_contract_accepts_expected_index_fixture(self) -> None:
        content = fixture_path("app_exports", "export-public-calls.html").read_bytes()

        result = evaluate_app_source_contract(content)

        self.assertEqual(result["source_name"], "app_exports")
        self.assertEqual(result["checks"]["parsed_year_count"], 3)
        self.assertTrue(result["checks"]["download_hint_present"])

    def test_evaluate_app_source_contract_rejects_missing_download_hint(self) -> None:
        content = b"<html><body><table><tr><td>2026</td><td>file.csv</td></tr></table></body></html>"

        with self.assertRaises(SmokeCheckFailure):
            evaluate_app_source_contract(content)

    def test_evaluate_qkb_search_source_contract_accepts_expected_form(self) -> None:
        content = b"""
        <html>
          <body>
            <form method="post">
              <input id="nipt" name="nipt" />
              <input id="dataNga" name="dataNga" />
              <input id="dataNe" name="dataNe" />
              <button type="submit">Kerko</button>
            </form>
          </body>
        </html>
        """

        result = evaluate_qkb_search_source_contract(content)

        self.assertEqual(result["source_name"], "qkb_search")
        self.assertTrue(result["checks"]["nipt_field_present"])
        self.assertTrue(result["checks"]["data_nga_field_present"])
        self.assertTrue(result["checks"]["data_ne_field_present"])
        self.assertTrue(result["checks"]["submit_controls_present"])

    def test_evaluate_qkb_search_source_contract_rejects_missing_selector(self) -> None:
        content = b"""
        <html>
          <body>
            <form method="post">
              <input id="nipt" name="nipt" />
              <input id="dataNga" name="dataNga" />
              <button type="submit">Kerko</button>
            </form>
          </body>
        </html>
        """

        with self.assertRaises(SmokeCheckFailure):
            evaluate_qkb_search_source_contract(content)


if __name__ == "__main__":
    unittest.main()
