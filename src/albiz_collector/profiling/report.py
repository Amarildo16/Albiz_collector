from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..features.registry import FeatureDefinition, get_feature_registry
from ..models import (
    AppCompanyFeature,
    JoinedCompanyFeature,
    NormalizedAppExportRow,
    NormalizedQkbSearchRow,
    QkbCompanyFeature,
)


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def _missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _field_profile(rows: list[Any], field_name: str) -> dict[str, Any]:
    total = len(rows)
    missing = sum(1 for row in rows if _missing_value(getattr(row, field_name)))
    present = total - missing
    return {
        "field": field_name,
        "total_rows": total,
        "present_count": present,
        "missing_count": missing,
        "present_rate": _rate(present, total),
        "missing_rate": _rate(missing, total),
    }


def _distinct_identifiers(values: Iterable[str | None]) -> set[str]:
    distinct: set[str] = set()
    for value in values:
        normalized = _normalize_identifier(value)
        if normalized is not None:
            distinct.add(normalized)
    return distinct


def _row_count_profile(rows: list[Any], dataset_name: str) -> dict[str, Any]:
    return {"dataset": dataset_name, "row_count": len(rows)}


def _feature_field_profiles(rows: list[Any], feature_definitions: tuple[FeatureDefinition, ...]) -> dict[str, Any]:
    profiles = []
    for feature in feature_definitions:
        field_stats = _field_profile(rows, feature.name)
        profiles.append(
            {
                "name": feature.name,
                "category": feature.category,
                "confidence": feature.confidence,
                "description": feature.description,
                "present_count": field_stats["present_count"],
                "missing_count": field_stats["missing_count"],
                "present_rate": field_stats["present_rate"],
                "missing_rate": field_stats["missing_rate"],
            }
        )
    return {"feature_profiles": profiles}


def _feature_table_readiness(dataset_name: str, row_count: int, high_confidence_present_rate: float) -> dict[str, Any]:
    if row_count == 0:
        return {
            "dataset": dataset_name,
            "status": "blocked",
            "reason": "No rows are currently materialized for this feature table.",
        }
    if high_confidence_present_rate >= 0.75:
        return {
            "dataset": dataset_name,
            "status": "usable_now",
            "reason": "Core high-confidence features are mostly populated in the current local dataset.",
        }
    return {
        "dataset": dataset_name,
        "status": "usable_with_caution",
        "reason": "The table exists, but high-confidence feature coverage is limited in the current local dataset.",
    }


def profile_normalized_data(db: Session) -> dict[str, Any]:
    app_rows = db.scalars(select(NormalizedAppExportRow).order_by(NormalizedAppExportRow.id)).all()
    qkb_rows = db.scalars(select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.id)).all()

    app_winner_nipts = _distinct_identifiers(row.winner_nipt for row in app_rows)
    qkb_business_nipts = _distinct_identifiers(row.business_nipt for row in qkb_rows)
    exact_joinable_nipts = app_winner_nipts & qkb_business_nipts
    app_rows_with_winner_nipt = sum(1 for row in app_rows if _normalize_identifier(row.winner_nipt) is not None)
    qkb_rows_with_business_nipt = sum(1 for row in qkb_rows if _normalize_identifier(row.business_nipt) is not None)
    app_rows_joinable = sum(
        1
        for row in app_rows
        if (_normalize_identifier(row.winner_nipt) or "") in exact_joinable_nipts
    )
    qkb_rows_joinable = sum(
        1
        for row in qkb_rows
        if (_normalize_identifier(row.business_nipt) or "") in exact_joinable_nipts
    )

    result = {
        "row_counts": {
            "normalized_app_export_rows": len(app_rows),
            "normalized_qkb_search_rows": len(qkb_rows),
        },
        "app_summary": {
            "distinct_procurement_references": len(_distinct_identifiers(row.procurement_reference for row in app_rows)),
            "distinct_winner_nipts": len(app_winner_nipts),
            "winner_nipt_coverage": {
                "present_count": app_rows_with_winner_nipt,
                "missing_count": len(app_rows) - app_rows_with_winner_nipt,
                "present_rate": _rate(app_rows_with_winner_nipt, len(app_rows)),
                "missing_rate": _rate(len(app_rows) - app_rows_with_winner_nipt, len(app_rows)),
            },
            "important_field_missingness": {
                "publication_date": _field_profile(app_rows, "publication_date"),
                "budget_limit_amount": _field_profile(app_rows, "budget_limit_amount"),
                "winner_value_amount": _field_profile(app_rows, "winner_value_amount"),
                "procedure_type": _field_profile(app_rows, "procedure_type"),
                "contract_type": _field_profile(app_rows, "contract_type"),
            },
        },
        "qkb_summary": {
            "distinct_business_nipts": len(qkb_business_nipts),
            "business_nipt_coverage": {
                "present_count": qkb_rows_with_business_nipt,
                "missing_count": len(qkb_rows) - qkb_rows_with_business_nipt,
                "present_rate": _rate(qkb_rows_with_business_nipt, len(qkb_rows)),
                "missing_rate": _rate(len(qkb_rows) - qkb_rows_with_business_nipt, len(qkb_rows)),
            },
            "important_field_missingness": {
                "business_name": _field_profile(qkb_rows, "business_name"),
                "legal_form": _field_profile(qkb_rows, "legal_form"),
                "subject_status": _field_profile(qkb_rows, "subject_status"),
                "registration_date": _field_profile(qkb_rows, "registration_date"),
                "city": _field_profile(qkb_rows, "city"),
                "has_red_flags": _field_profile(qkb_rows, "has_red_flags"),
            },
        },
        "join_coverage": {
            "app_distinct_winner_nipts": len(app_winner_nipts),
            "qkb_distinct_business_nipts": len(qkb_business_nipts),
            "exact_joinable_company_nipts": len(exact_joinable_nipts),
            "app_rows_with_winner_nipt": app_rows_with_winner_nipt,
            "qkb_rows_with_business_nipt": qkb_rows_with_business_nipt,
            "app_rows_joinable_exact": app_rows_joinable,
            "qkb_rows_joinable_exact": qkb_rows_joinable,
            "app_joinable_rate_over_all_rows": _rate(app_rows_joinable, len(app_rows)),
            "app_joinable_rate_over_rows_with_winner_nipt": _rate(app_rows_joinable, app_rows_with_winner_nipt),
            "qkb_joinable_rate_over_all_rows": _rate(qkb_rows_joinable, len(qkb_rows)),
            "qkb_joinable_rate_over_rows_with_business_nipt": _rate(qkb_rows_joinable, qkb_rows_with_business_nipt),
        },
    }
    return result


def profile_feature_data(db: Session) -> dict[str, Any]:
    app_rows = db.scalars(select(AppCompanyFeature).order_by(AppCompanyFeature.id)).all()
    qkb_rows = db.scalars(select(QkbCompanyFeature).order_by(QkbCompanyFeature.id)).all()
    joined_rows = db.scalars(select(JoinedCompanyFeature).order_by(JoinedCompanyFeature.id)).all()
    registry = get_feature_registry()

    app_profiles = _feature_field_profiles(app_rows, registry["app_company_features"])
    qkb_profiles = _feature_field_profiles(qkb_rows, registry["qkb_company_features"])
    joined_profiles = _feature_field_profiles(joined_rows, registry["joined_company_features"])

    def _confidence_coverage(profiles: dict[str, Any], confidence: str) -> float:
        matching = [item for item in profiles["feature_profiles"] if item["confidence"] == confidence]
        if not matching:
            return 0.0
        average = sum(item["present_rate"] for item in matching) / len(matching)
        return round(average, 4)

    return {
        "row_counts": {
            "app_company_features": len(app_rows),
            "qkb_company_features": len(qkb_rows),
            "joined_company_features": len(joined_rows),
        },
        "feature_sparsity": {
            "app_company_features": app_profiles,
            "qkb_company_features": qkb_profiles,
            "joined_company_features": joined_profiles,
        },
        "readiness": {
            "app_company_features": _feature_table_readiness(
                "app_company_features",
                len(app_rows),
                _confidence_coverage(app_profiles, "safe"),
            ),
            "qkb_company_features": _feature_table_readiness(
                "qkb_company_features",
                len(qkb_rows),
                _confidence_coverage(qkb_profiles, "safe"),
            ),
            "joined_company_features": _feature_table_readiness(
                "joined_company_features",
                len(joined_rows),
                _confidence_coverage(joined_profiles, "safe"),
            ),
        },
    }


def profile_all_data(db: Session) -> dict[str, Any]:
    normalized = profile_normalized_data(db)
    features = profile_feature_data(db)

    joinable = normalized["join_coverage"]["exact_joinable_company_nipts"]
    qkb_rows = normalized["row_counts"]["normalized_qkb_search_rows"]
    app_rows = normalized["row_counts"]["normalized_app_export_rows"]
    winner_nipt_missing_rate = normalized["app_summary"]["winner_nipt_coverage"]["missing_rate"]

    strengths: list[str] = []
    weaknesses: list[str] = []
    blockers: list[str] = []
    usable_now: list[str] = []
    backfill_priority: list[str] = []

    if app_rows > 0:
        strengths.append("APP normalized procurement rows are present and support procurement-side analysis.")
    if normalized["app_summary"]["important_field_missingness"]["publication_date"]["present_rate"] > 0.9:
        strengths.append("APP publication dates are mostly populated, which supports chronology-based analysis.")
    if qkb_rows > 0:
        strengths.append("QKB registry rows are present and support company-level registry enrichment where exact NIPT matches exist.")
    if features["row_counts"]["app_company_features"] > 0:
        usable_now.append("APP company features are usable now for procurement exposure and outcome analysis on rows with winner NIPT.")
    if features["row_counts"]["qkb_company_features"] > 0:
        usable_now.append("QKB company features are usable now for registry-context analysis on collected business NIPTs.")
    if features["row_counts"]["joined_company_features"] > 0:
        usable_now.append("Joined APP to QKB features are usable now for exact-match company enrichment.")

    if winner_nipt_missing_rate > 0.1:
        weaknesses.append("A meaningful share of APP rows lack winner NIPT, which limits company-level aggregation and exact joins.")
    if qkb_rows == 0:
        blockers.append("No QKB normalized rows are present, so registry enrichment is currently blocked.")
    elif qkb_rows < 25:
        weaknesses.append("Current QKB local coverage is small, so registry-side analysis is still thin even though the table works.")
    if joinable == 0:
        blockers.append("There are currently no exact APP to QKB company joins in the local dataset.")
    elif joinable < 10:
        weaknesses.append("Exact APP to QKB join coverage exists but is still too small for broad joined analysis.")

    if joinable == 0:
        backfill_priority.append("Backfill QKB searches for APP winner NIPTs to increase exact join coverage.")
    if winner_nipt_missing_rate > 0.1:
        backfill_priority.append("Investigate APP winner identifier completeness before relying on company-level APP analysis alone.")
    if normalized["qkb_summary"]["important_field_missingness"]["registration_date"]["missing_rate"] > 0.2:
        backfill_priority.append("Improve QKB registration-date coverage before leaning on age-at-procurement features.")
    if features["row_counts"]["joined_company_features"] == 0:
        backfill_priority.append("Treat joined feature analysis as blocked until exact-match company rows are materialized.")

    return {
        "normalized": normalized,
        "features": features,
        "analytical_readiness": {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "blockers": blockers,
            "usable_feature_families_now": usable_now,
            "priority_backfill_actions": backfill_priority,
        },
    }