from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FeatureConfidence = Literal["safe", "caution", "not_recommended"]


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    dataset: str
    category: str
    confidence: FeatureConfidence
    description: str


APP_FEATURES: tuple[FeatureDefinition, ...] = (
    FeatureDefinition("source_row_count", "app_company_features", "participation", "safe", "Count of normalized APP rows for an exact winner NIPT."),
    FeatureDefinition("active_procurement_count", "app_company_features", "participation", "safe", "Count of APP rows for the winner NIPT where the procurement is not cancelled."),
    FeatureDefinition("cancelled_procurement_count", "app_company_features", "participation", "safe", "Count of APP rows marked cancelled."),
    FeatureDefinition("suspended_procurement_count", "app_company_features", "participation", "safe", "Count of APP rows marked suspended."),
    FeatureDefinition("cancelled_procurement_rate", "app_company_features", "participation_rate", "caution", "Share of APP rows for the winner NIPT marked cancelled."),
    FeatureDefinition("suspended_procurement_rate", "app_company_features", "participation_rate", "caution", "Share of APP rows for the winner NIPT marked suspended."),
    FeatureDefinition("total_budget_limit_amount", "app_company_features", "outcome_value", "safe", "Sum of APP budget limit amounts where present."),
    FeatureDefinition("total_winner_value_amount", "app_company_features", "outcome_value", "safe", "Sum of APP winner value amounts where present."),
    FeatureDefinition("active_total_budget_limit_amount", "app_company_features", "outcome_value", "safe", "Sum of APP budget limit amounts on non-cancelled rows where present."),
    FeatureDefinition("active_total_winner_value_amount", "app_company_features", "outcome_value", "safe", "Sum of APP winner value amounts on non-cancelled rows where present."),
    FeatureDefinition("cancelled_total_budget_limit_amount", "app_company_features", "outcome_value", "safe", "Sum of APP budget limit amounts on cancelled rows where present."),
    FeatureDefinition("cancelled_total_winner_value_amount", "app_company_features", "outcome_value", "safe", "Sum of APP winner value amounts on cancelled rows where present."),
    FeatureDefinition("safe_winner_to_budget_ratio_avg", "app_company_features", "ratio", "caution", "Average winner value divided by positive budget limit, excluding zero or missing budgets."),
    FeatureDefinition("safe_winner_to_budget_ratio_min", "app_company_features", "ratio", "caution", "Minimum winner value divided by positive budget limit, excluding zero or missing budgets."),
    FeatureDefinition("safe_winner_to_budget_ratio_max", "app_company_features", "ratio", "caution", "Maximum winner value divided by positive budget limit, excluding zero or missing budgets."),
    FeatureDefinition("purchase_tickets_count", "app_company_features", "purchase_tickets", "caution", "Count of APP rows whose procedure type is Purchase Tickets."),
    FeatureDefinition("purchase_tickets_total_winner_value", "app_company_features", "purchase_tickets", "caution", "Sum of winner values on APP Purchase Tickets rows where present."),
    FeatureDefinition("zero_budget_with_winner_value_count", "app_company_features", "data_quality", "safe", "Count of APP rows with zero budget limit and present winner value."),
    FeatureDefinition("zero_budget_with_winner_value_rate", "app_company_features", "data_quality", "caution", "Share of APP rows with zero budget limit and present winner value."),
    FeatureDefinition("first_procurement_date", "app_company_features", "temporal", "safe", "Earliest APP publication date observed for the winner NIPT."),
    FeatureDefinition("last_procurement_date", "app_company_features", "temporal", "safe", "Latest APP publication date observed for the winner NIPT."),
    FeatureDefinition("first_procurement_year", "app_company_features", "temporal", "safe", "Year of the earliest APP publication date observed for the winner NIPT."),
    FeatureDefinition("last_procurement_year", "app_company_features", "temporal", "safe", "Year of the latest APP publication date observed for the winner NIPT."),
    FeatureDefinition("active_year_span", "app_company_features", "temporal", "safe", "Inclusive calendar-year span between first and last APP publication dates."),
    FeatureDefinition("distinct_contracting_authority_count", "app_company_features", "context", "caution", "Distinct contracting authorities linked to the winner NIPT."),
    FeatureDefinition("distinct_procedure_type_count", "app_company_features", "context", "caution", "Distinct APP procedure types linked to the winner NIPT."),
    FeatureDefinition("distinct_contract_type_count", "app_company_features", "context", "caution", "Distinct APP contract types linked to the winner NIPT."),
    FeatureDefinition("has_small_value_procedures", "app_company_features", "context", "caution", "Indicator that at least one APP procedure type mentions Small Value."),
    FeatureDefinition("has_open_local_procedures", "app_company_features", "context", "caution", "Indicator that at least one APP procedure type mentions Open Local."),
    FeatureDefinition("rows_with_winner_value_count", "app_company_features", "support", "safe", "Count of APP rows with a present winner value amount."),
    FeatureDefinition("rows_with_budget_count", "app_company_features", "support", "safe", "Count of APP rows with a present budget limit amount, including zero budgets."),
    FeatureDefinition("rows_with_valid_ratio_count", "app_company_features", "support", "safe", "Count of APP rows eligible for safe winner-to-budget ratio calculation."),
)

QKB_FEATURES: tuple[FeatureDefinition, ...] = (
    FeatureDefinition("business_name", "qkb_company_features", "identity", "safe", "Latest representative business name for the exact company NIPT."),
    FeatureDefinition("legal_form", "qkb_company_features", "identity", "safe", "Latest representative legal form for the exact company NIPT."),
    FeatureDefinition("subject_status", "qkb_company_features", "status", "safe", "Latest representative registry status."),
    FeatureDefinition("registration_date", "qkb_company_features", "temporal", "safe", "Registration date used for later age-based joins."),
    FeatureDefinition("registration_year", "qkb_company_features", "temporal", "safe", "Registration year derived from registration date when present."),
    FeatureDefinition("city", "qkb_company_features", "context", "caution", "Registry city retained as contextual metadata, not as a join key."),
    FeatureDefinition("has_red_flags", "qkb_company_features", "risk", "caution", "Registry red-flag boolean retained as a source-side signal, not a target label."),
    FeatureDefinition("has_activity_text", "qkb_company_features", "context", "caution", "Presence indicator for activity text without promoting raw text to a strong feature."),
    FeatureDefinition("has_ownership_text", "qkb_company_features", "context", "caution", "Presence indicator for ownership text without promoting raw text to a strong feature."),
)

JOINED_FEATURES: tuple[FeatureDefinition, ...] = (
    FeatureDefinition("exact_join_match", "joined_company_features", "join", "safe", "Boolean indicator that the joined feature row was created via exact NIPT equality."),
    FeatureDefinition("source_row_count", "joined_company_features", "participation", "safe", "APP source row count copied from app company features for the exact joined NIPT."),
    FeatureDefinition("active_procurement_count", "joined_company_features", "participation", "safe", "Count of non-cancelled APP rows copied for the exact joined NIPT."),
    FeatureDefinition("cancelled_procurement_count", "joined_company_features", "participation", "safe", "Count of cancelled APP rows copied for the exact joined NIPT."),
    FeatureDefinition("suspended_procurement_count", "joined_company_features", "participation", "safe", "Count of suspended APP rows copied for the exact joined NIPT."),
    FeatureDefinition("cancelled_procurement_rate", "joined_company_features", "participation_rate", "caution", "Share of APP rows marked cancelled for the exact joined NIPT."),
    FeatureDefinition("suspended_procurement_rate", "joined_company_features", "participation_rate", "caution", "Share of APP rows marked suspended for the exact joined NIPT."),
    FeatureDefinition("total_budget_limit_amount", "joined_company_features", "outcome_value", "safe", "APP total budget limit amount copied for the exact joined NIPT."),
    FeatureDefinition("total_winner_value_amount", "joined_company_features", "outcome_value", "safe", "APP total winner value amount copied for the exact joined NIPT."),
    FeatureDefinition("active_total_budget_limit_amount", "joined_company_features", "outcome_value", "safe", "APP budget limit sum on non-cancelled rows copied for the exact joined NIPT."),
    FeatureDefinition("active_total_winner_value_amount", "joined_company_features", "outcome_value", "safe", "APP winner value sum on non-cancelled rows copied for the exact joined NIPT."),
    FeatureDefinition("cancelled_total_budget_limit_amount", "joined_company_features", "outcome_value", "safe", "APP budget limit sum on cancelled rows copied for the exact joined NIPT."),
    FeatureDefinition("cancelled_total_winner_value_amount", "joined_company_features", "outcome_value", "safe", "APP winner value sum on cancelled rows copied for the exact joined NIPT."),
    FeatureDefinition("safe_winner_to_budget_ratio_avg", "joined_company_features", "ratio", "caution", "APP average winner-to-positive-budget ratio copied for the exact joined NIPT."),
    FeatureDefinition("safe_winner_to_budget_ratio_min", "joined_company_features", "ratio", "caution", "APP minimum winner-to-positive-budget ratio copied for the exact joined NIPT."),
    FeatureDefinition("safe_winner_to_budget_ratio_max", "joined_company_features", "ratio", "caution", "APP maximum winner-to-positive-budget ratio copied for the exact joined NIPT."),
    FeatureDefinition("purchase_tickets_count", "joined_company_features", "purchase_tickets", "caution", "Count of APP Purchase Tickets rows copied for the exact joined NIPT."),
    FeatureDefinition("purchase_tickets_total_winner_value", "joined_company_features", "purchase_tickets", "caution", "Winner value sum on APP Purchase Tickets rows copied for the exact joined NIPT."),
    FeatureDefinition("zero_budget_with_winner_value_count", "joined_company_features", "data_quality", "safe", "Count of APP zero-budget rows with winner value copied for the exact joined NIPT."),
    FeatureDefinition("zero_budget_with_winner_value_rate", "joined_company_features", "data_quality", "caution", "Share of APP zero-budget rows with winner value copied for the exact joined NIPT."),
    FeatureDefinition("first_procurement_date", "joined_company_features", "temporal", "safe", "Earliest APP publication date copied for the exact joined NIPT."),
    FeatureDefinition("last_procurement_date", "joined_company_features", "temporal", "safe", "Latest APP publication date copied for the exact joined NIPT."),
    FeatureDefinition("first_procurement_year", "joined_company_features", "temporal", "safe", "Year of earliest APP publication date copied for the exact joined NIPT."),
    FeatureDefinition("last_procurement_year", "joined_company_features", "temporal", "safe", "Year of latest APP publication date copied for the exact joined NIPT."),
    FeatureDefinition("active_year_span", "joined_company_features", "temporal", "safe", "Inclusive APP publication-year span copied for the exact joined NIPT."),
    FeatureDefinition("company_age_days_at_first_procurement", "joined_company_features", "temporal", "safe", "Days between company registration and earliest observed procurement publication date when both dates exist."),
    FeatureDefinition("company_age_days_at_last_procurement", "joined_company_features", "temporal", "safe", "Days between company registration and latest observed procurement publication date when both dates exist."),
    FeatureDefinition("distinct_contracting_authority_count", "joined_company_features", "context", "caution", "Distinct APP contracting-authority count copied for the exact joined NIPT."),
    FeatureDefinition("distinct_procedure_type_count", "joined_company_features", "context", "caution", "Distinct APP procedure-type count copied for the exact joined NIPT."),
    FeatureDefinition("distinct_contract_type_count", "joined_company_features", "context", "caution", "Distinct APP contract-type count copied for the exact joined NIPT."),
    FeatureDefinition("has_small_value_procedures", "joined_company_features", "context", "caution", "Indicator copied from APP features for Small Value procedure exposure."),
    FeatureDefinition("has_open_local_procedures", "joined_company_features", "context", "caution", "Indicator copied from APP features for Open Local procedure exposure."),
    FeatureDefinition("rows_with_winner_value_count", "joined_company_features", "support", "safe", "Count of APP rows with present winner value copied for the exact joined NIPT."),
    FeatureDefinition("rows_with_budget_count", "joined_company_features", "support", "safe", "Count of APP rows with present budget limit copied for the exact joined NIPT."),
    FeatureDefinition("rows_with_valid_ratio_count", "joined_company_features", "support", "safe", "Count of APP rows eligible for safe ratio calculation copied for the exact joined NIPT."),
    FeatureDefinition("business_name", "joined_company_features", "registry_enrichment", "safe", "Registry business name copied only for exact NIPT joins."),
    FeatureDefinition("legal_form", "joined_company_features", "registry_enrichment", "safe", "Registry legal form copied only for exact NIPT joins."),
    FeatureDefinition("subject_status", "joined_company_features", "registry_enrichment", "safe", "Registry status copied only for exact NIPT joins."),
    FeatureDefinition("registration_date", "joined_company_features", "registry_enrichment", "safe", "Registry registration date copied only for exact NIPT joins."),
    FeatureDefinition("registration_year", "joined_company_features", "registry_enrichment", "safe", "Registry registration year copied only for exact NIPT joins."),
    FeatureDefinition("city", "joined_company_features", "registry_enrichment", "caution", "Registry city copied as context only for exact NIPT joins."),
    FeatureDefinition("has_red_flags", "joined_company_features", "risk", "caution", "Registry red-flag signal copied only for exact NIPT joins."),
    FeatureDefinition("has_activity_text", "joined_company_features", "registry_context", "caution", "Presence indicator for QKB activity text copied only for exact NIPT joins."),
    FeatureDefinition("has_ownership_text", "joined_company_features", "registry_context", "caution", "Presence indicator for QKB ownership text copied only for exact NIPT joins."),
)


def get_feature_registry() -> dict[str, tuple[FeatureDefinition, ...]]:
    return {
        "app_company_features": APP_FEATURES,
        "qkb_company_features": QKB_FEATURES,
        "joined_company_features": JOINED_FEATURES,
    }
