from __future__ import annotations

import unittest

from albiz_collector.semantics.research_dataset import (
    APP_EXPORT_DATASET,
    QKB_SEARCH_DATASET,
    RESEARCH_JOIN_POLICY,
    assess_app_qkb_join,
    get_dataset_semantics,
)


class ResearchDatasetSemanticsTests(unittest.TestCase):
    def test_get_dataset_semantics_returns_known_datasets(self) -> None:
        app_dataset = get_dataset_semantics("normalized_app_export_rows")
        qkb_dataset = get_dataset_semantics("normalized_qkb_search_rows")

        self.assertEqual(app_dataset.analytical_unit, APP_EXPORT_DATASET.analytical_unit)
        self.assertEqual(qkb_dataset.safe_join_fields, ("business_nipt",))

    def test_safe_join_requires_exact_nipt_match(self) -> None:
        assessment = assess_app_qkb_join("L47230701F", "l47230701f")

        self.assertEqual(assessment.status, "safe")
        self.assertEqual(assessment.strategy, "exact_nipt")

    def test_name_only_join_is_caution_not_default(self) -> None:
        assessment = assess_app_qkb_join(
            None,
            None,
            app_winner_name="Future Block Group",
            qkb_business_name="Future Block Group",
        )

        self.assertEqual(assessment.status, "caution")
        self.assertEqual(assessment.strategy, "manual_name_review_only")

    def test_conflicting_nipts_block_join(self) -> None:
        assessment = assess_app_qkb_join("L47230701F", "M21528028T")

        self.assertEqual(assessment.status, "avoid")
        self.assertEqual(assessment.strategy, "nipt_conflict")

    def test_join_policy_states_exact_nipt_as_primary_default(self) -> None:
        self.assertEqual(RESEARCH_JOIN_POLICY.primary_key, "winner_nipt -> business_nipt")
        self.assertIn("Exact APP winner_nipt == QKB business_nipt", RESEARCH_JOIN_POLICY.safe_joins)


if __name__ == "__main__":
    unittest.main()