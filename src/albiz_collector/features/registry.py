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
    FeatureDefinition("first_procurement_date", "app_company_features", "temporal", "safe", "Earliest APP publication date observed for the winner NIPT."),
    FeatureDefinition("last_procurement_date", "app_company_features", "temporal", "safe", "Latest APP publication date observed for the winner NIPT."),
    FeatureDefinition("total_budget_limit_amount", "app_company_features", "outcome_value", "safe", "Sum of APP budget limit amounts where present."),
    FeatureDefinition("total_winner_value_amount", "app_company_features", "outcome_value", "safe", "Sum of APP winner value amounts where present."),
    FeatureDefinition("cancelled_procurement_count", "app_company_features", "risk", "safe", "Count of APP rows marked cancelled."),
    FeatureDefinition("suspended_procurement_count", "app_company_features", "risk", "safe", "Count of APP rows marked suspended."),
    FeatureDefinition("distinct_contracting_authority_count", "app_company_features", "context", "safe", "Distinct contracting authorities linked to the winner NIPT."),
    FeatureDefinition("has_small_value_procedures", "app_company_features", "context", "caution", "Indicator that at least one APP procedure type mentions Small Value."),
    FeatureDefinition("has_open_local_procedures", "app_company_features", "context", "caution", "Indicator that at least one APP procedure type mentions Open Local."),
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
    FeatureDefinition("company_age_days_at_first_procurement", "joined_company_features", "temporal", "safe", "Days between company registration and earliest observed procurement publication date when both dates exist."),
    FeatureDefinition("company_age_days_at_last_procurement", "joined_company_features", "temporal", "safe", "Days between company registration and latest observed procurement publication date when both dates exist."),
    FeatureDefinition("legal_form", "joined_company_features", "registry_enrichment", "safe", "Registry legal form copied only for exact NIPT joins."),
    FeatureDefinition("subject_status", "joined_company_features", "registry_enrichment", "safe", "Registry status copied only for exact NIPT joins."),
    FeatureDefinition("city", "joined_company_features", "registry_enrichment", "caution", "Registry city copied as context only for exact NIPT joins."),
    FeatureDefinition("has_red_flags", "joined_company_features", "risk", "caution", "Registry red-flag signal copied only for exact NIPT joins."),
)


def get_feature_registry() -> dict[str, tuple[FeatureDefinition, ...]]:
    return {
        "app_company_features": APP_FEATURES,
        "qkb_company_features": QKB_FEATURES,
        "joined_company_features": JOINED_FEATURES,
    }