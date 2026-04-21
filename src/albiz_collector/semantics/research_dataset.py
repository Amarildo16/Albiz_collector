from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SemanticRole = Literal[
    "core_identity",
    "join_candidate",
    "performance_signal",
    "risk_signal",
    "temporal",
    "context_metadata",
    "weak_or_noisy",
]
UsageLevel = Literal["safe", "caution", "avoid"]


@dataclass(frozen=True)
class FieldSemantic:
    field_name: str
    role: SemanticRole
    usage_level: UsageLevel
    note: str


@dataclass(frozen=True)
class DatasetSemantics:
    dataset_name: str
    analytical_unit: str
    description: str
    field_semantics: tuple[FieldSemantic, ...]
    safe_join_fields: tuple[str, ...]
    cautious_join_fields: tuple[str, ...]
    avoid_join_fields: tuple[str, ...]
    feature_candidates: dict[str, tuple[str, ...]]
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class JoinAssessment:
    status: UsageLevel
    strategy: str
    reason: str


@dataclass(frozen=True)
class JoinPolicy:
    primary_key: str
    safe_joins: tuple[str, ...]
    risky_joins: tuple[str, ...]
    joins_to_avoid: tuple[str, ...]
    default_policy: str


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def assess_app_qkb_join(
    app_winner_nipt: str | None,
    qkb_business_nipt: str | None,
    app_winner_name: str | None = None,
    qkb_business_name: str | None = None,
) -> JoinAssessment:
    left_nipt = _normalize_identifier(app_winner_nipt)
    right_nipt = _normalize_identifier(qkb_business_nipt)

    if left_nipt and right_nipt and left_nipt == right_nipt:
        return JoinAssessment(
            status="safe",
            strategy="exact_nipt",
            reason="Exact NIPT equality is the strongest traceable APP to QKB join in the current dataset.",
        )

    if left_nipt and right_nipt and left_nipt != right_nipt:
        return JoinAssessment(
            status="avoid",
            strategy="nipt_conflict",
            reason="Conflicting NIPTs should block the join even if other text fields look similar.",
        )

    if (app_winner_name or "").strip() and (qkb_business_name or "").strip():
        return JoinAssessment(
            status="caution",
            strategy="manual_name_review_only",
            reason="Name-only matching may help manual review, but it is not a safe default analytical join.",
        )

    return JoinAssessment(
        status="avoid",
        strategy="insufficient_identifier",
        reason="Missing exact business identifiers means the rows should remain in separate source datasets.",
    )


APP_EXPORT_DATASET = DatasetSemantics(
    dataset_name="normalized_app_export_rows",
    analytical_unit="one procurement row from one APP export year CSV",
    description="Procurement exposure and award-outcome records materialized from APP export CSV rows.",
    field_semantics=(
        FieldSemantic("procurement_reference", "core_identity", "safe", "Best row-level procurement identifier currently present in APP exports."),
        FieldSemantic("export_year", "context_metadata", "safe", "Stable snapshot context from the exported APP file."),
        FieldSemantic("winner_nipt", "join_candidate", "safe", "Safest APP-side company join field when present."),
        FieldSemantic("winner_name", "join_candidate", "caution", "Useful for manual review, but weaker than NIPT due to spelling and formatting drift."),
        FieldSemantic("contracting_authority", "context_metadata", "safe", "Stable source-side organization context for the procurement row."),
        FieldSemantic("procurement_subject", "context_metadata", "caution", "Useful analytical text, but free text and not suitable as an identifier."),
        FieldSemantic("procedure_type", "performance_signal", "safe", "Operational procurement context that can be grouped reliably enough for analysis."),
        FieldSemantic("contract_type", "performance_signal", "safe", "Operational procurement context that can be grouped reliably enough for analysis."),
        FieldSemantic("publication_date", "temporal", "safe", "Most useful APP-side timing field for basic chronology."),
        FieldSemantic("opening_date", "temporal", "caution", "Useful timing field, but sometimes more operational than analytical."),
        FieldSemantic("closing_date", "temporal", "caution", "Useful timing field, but may vary in interpretation across rows."),
        FieldSemantic("budget_limit_amount", "performance_signal", "safe", "Useful value proxy for procurement size or exposure."),
        FieldSemantic("winner_value_amount", "performance_signal", "safe", "Useful outcome value field when populated."),
        FieldSemantic("is_cancelled", "risk_signal", "safe", "Reasonably clear operational risk/outcome indicator."),
        FieldSemantic("is_suspended", "risk_signal", "safe", "Reasonably clear operational risk/outcome indicator."),
        FieldSemantic("cpv_codes", "context_metadata", "caution", "Useful sector/category context, but still semi-structured text."),
        FieldSemantic("source_payload", "weak_or_noisy", "caution", "Retained for traceability and later manual interpretation, not as a first-class feature block."),
    ),
    safe_join_fields=("winner_nipt",),
    cautious_join_fields=("winner_name",),
    avoid_join_fields=("procurement_subject", "contracting_authority"),
    feature_candidates={
        "procurement_outcome": (
            "budget_limit_amount",
            "winner_value_amount",
            "is_cancelled",
            "is_suspended",
            "procedure_type",
            "contract_type",
        ),
        "temporal": ("publication_date", "opening_date", "closing_date", "export_year"),
        "entity_context": ("winner_nipt", "winner_name", "contracting_authority", "cpv_codes"),
    },
    caveats=(
        "APP rows describe procurement events, not companies directly.",
        "Many APP rows may lack winner NIPT, so they cannot be safely joined to registry data.",
        "Free-text subject fields are useful context, but not defensible identity keys.",
    ),
)


QKB_SEARCH_DATASET = DatasetSemantics(
    dataset_name="normalized_qkb_search_rows",
    analytical_unit="one business result row returned by one QKB subject-search snapshot",
    description="Registry identity and status records materialized from QKB subject-search results.",
    field_semantics=(
        FieldSemantic("business_nipt", "core_identity", "safe", "Strongest company identifier in the QKB search dataset."),
        FieldSemantic("business_name", "core_identity", "safe", "Useful business label, but still subordinate to NIPT for joins."),
        FieldSemantic("trade_name", "context_metadata", "caution", "Helpful label when present, but less stable than formal business name."),
        FieldSemantic("search_nipt", "join_candidate", "caution", "Useful search provenance, but not a row identity field."),
        FieldSemantic("legal_form", "context_metadata", "safe", "Stable-enough registry classification field for downstream grouping."),
        FieldSemantic("registration_date", "temporal", "safe", "Strong registry timing field for age-based analysis."),
        FieldSemantic("city", "context_metadata", "caution", "Useful location context, but not strong enough for matching on its own."),
        FieldSemantic("ownership_text", "risk_signal", "caution", "Potentially useful structure/ownership context, but still textual."),
        FieldSemantic("subject_status", "risk_signal", "safe", "Useful registry-state field for downstream interpretation."),
        FieldSemantic("subject_type", "weak_or_noisy", "caution", "Present but sometimes blank or weakly populated in current samples."),
        FieldSemantic("activity_text", "context_metadata", "caution", "Useful descriptive text, but free text rather than a stable coded field."),
        FieldSemantic("administrators_text", "weak_or_noisy", "caution", "Useful for manual context only; not a strong analytical join or feature by default."),
        FieldSemantic("has_red_flags", "risk_signal", "caution", "Potentially useful risk indicator, but meaning depends on QKB’s own presentation logic."),
        FieldSemantic("search_date_from", "temporal", "safe", "Useful search-window provenance for the snapshot."),
        FieldSemantic("search_date_to", "temporal", "safe", "Useful search-window provenance for the snapshot."),
        FieldSemantic("source_payload", "weak_or_noisy", "caution", "Retained for traceability and future interpretation, not as a default feature block."),
    ),
    safe_join_fields=("business_nipt",),
    cautious_join_fields=("business_name", "trade_name"),
    avoid_join_fields=("city", "activity_text", "administrators_text"),
    feature_candidates={
        "registry_identity": ("business_nipt", "business_name", "legal_form", "registration_date"),
        "registry_status": ("subject_status", "has_red_flags", "ownership_text"),
        "registry_context": ("city", "activity_text", "trade_name"),
    },
    caveats=(
        "QKB search results are registry-context rows, not observed business outcomes.",
        "Some registry fields are free text and should stay auxiliary until proven stable at scale.",
        "Search context fields describe how the row was collected, not intrinsic company properties.",
    ),
)


RESEARCH_JOIN_POLICY = JoinPolicy(
    primary_key="winner_nipt -> business_nipt",
    safe_joins=(
        "Exact APP winner_nipt == QKB business_nipt",
    ),
    risky_joins=(
        "Winner name vs business name manual review only",
        "Trade name comparisons as secondary human review context only",
    ),
    joins_to_avoid=(
        "Automatic name-only joins",
        "Address or city based joins",
        "Activity-text or contracting-authority text joins",
    ),
    default_policy="Keep APP and QKB as separate source datasets first; only materialize joined analytical rows when exact NIPT equality exists.",
)


def get_dataset_semantics(dataset_name: str) -> DatasetSemantics:
    mapping = {
        APP_EXPORT_DATASET.dataset_name: APP_EXPORT_DATASET,
        QKB_SEARCH_DATASET.dataset_name: QKB_SEARCH_DATASET,
    }
    try:
        return mapping[dataset_name]
    except KeyError as exc:
        raise ValueError(f"Unknown dataset semantics requested: {dataset_name}") from exc