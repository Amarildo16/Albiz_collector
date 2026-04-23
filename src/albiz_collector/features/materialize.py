from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    AppCompanyFeature,
    JoinedCompanyFeature,
    NormalizedAppExportRow,
    NormalizedQkbSearchRow,
    QkbCompanyFeature,
)
from ..semantics.research_dataset import assess_app_qkb_join
from ..utils.raw_fetches import exclude_corrupted_raw_fetches
from ..utils.time import utc_now_naive


def _base_stats(dataset: str, source_rows_seen: int) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "source_rows_seen": source_rows_seen,
        "rows_deleted_before_insert": 0,
        "rows_inserted": 0,
        "rows_materialized": 0,
        "groups_skipped": 0,
        "errors": [],
    }


def _decimal_sum(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0"))


def _latest_non_empty(rows: list[Any], field_name: str) -> str | None:
    for row in rows:
        value = getattr(row, field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _date_diff_days(start_date, end_date) -> int | None:
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


@dataclass(frozen=True)
class _FeatureInputs:
    app: dict[str, AppCompanyFeature]
    qkb: dict[str, QkbCompanyFeature]


def _build_app_features(rows: list[NormalizedAppExportRow]) -> tuple[list[AppCompanyFeature], int]:
    grouped: dict[str, list[NormalizedAppExportRow]] = defaultdict(list)
    skipped = 0
    for row in rows:
        if not row.winner_nipt:
            skipped += 1
            continue
        grouped[row.winner_nipt.strip().upper()].append(row)

    materialized_at = utc_now_naive()
    features: list[AppCompanyFeature] = []
    for company_nipt, company_rows in grouped.items():
        ordered_rows = sorted(
            company_rows,
            key=lambda item: (
                item.publication_date is not None,
                item.publication_date,
                item.materialized_at,
                item.id,
            ),
            reverse=True,
        )
        publication_dates = [row.publication_date for row in company_rows if row.publication_date is not None]
        budget_values = [Decimal(str(row.budget_limit_amount)) for row in company_rows if row.budget_limit_amount is not None]
        winner_values = [Decimal(str(row.winner_value_amount)) for row in company_rows if row.winner_value_amount is not None]
        procedure_types = {row.procedure_type.strip() for row in company_rows if row.procedure_type and row.procedure_type.strip()}
        contract_types = {row.contract_type.strip() for row in company_rows if row.contract_type and row.contract_type.strip()}
        authorities = {
            row.contracting_authority.strip()
            for row in company_rows
            if row.contracting_authority and row.contracting_authority.strip()
        }

        features.append(
            AppCompanyFeature(
                company_nipt=company_nipt,
                materialized_at=materialized_at,
                source_row_count=len(company_rows),
                source_snapshot_count=len({row.structured_record_id for row in company_rows}),
                source_structured_record_ids=sorted({row.structured_record_id for row in company_rows}),
                latest_winner_name=_latest_non_empty(ordered_rows, "winner_name"),
                first_procurement_date=min(publication_dates) if publication_dates else None,
                last_procurement_date=max(publication_dates) if publication_dates else None,
                total_budget_limit_amount=_decimal_sum(budget_values),
                total_winner_value_amount=_decimal_sum(winner_values),
                cancelled_procurement_count=sum(1 for row in company_rows if row.is_cancelled is True),
                suspended_procurement_count=sum(1 for row in company_rows if row.is_suspended is True),
                distinct_contracting_authority_count=len(authorities),
                distinct_procedure_type_count=len(procedure_types),
                distinct_contract_type_count=len(contract_types),
                has_small_value_procedures=any("small value" in value.lower() for value in procedure_types),
                has_open_local_procedures=any("open local" in value.lower() for value in procedure_types),
            )
        )

    return features, skipped


def _build_qkb_features(rows: list[NormalizedQkbSearchRow]) -> tuple[list[QkbCompanyFeature], int]:
    grouped: dict[str, list[NormalizedQkbSearchRow]] = defaultdict(list)
    skipped = 0
    for row in rows:
        if not row.business_nipt:
            skipped += 1
            continue
        grouped[row.business_nipt.strip().upper()].append(row)

    materialized_at = utc_now_naive()
    features: list[QkbCompanyFeature] = []
    for company_nipt, company_rows in grouped.items():
        ordered_rows = sorted(
            company_rows,
            key=lambda item: (
                item.search_date_to is not None,
                item.search_date_to,
                item.materialized_at,
                item.id,
            ),
            reverse=True,
        )
        representative = ordered_rows[0]
        registration_date = representative.registration_date
        features.append(
            QkbCompanyFeature(
                company_nipt=company_nipt,
                materialized_at=materialized_at,
                source_row_count=len(company_rows),
                source_snapshot_count=len({row.structured_record_id for row in company_rows}),
                source_structured_record_ids=sorted({row.structured_record_id for row in company_rows}),
                business_name=_latest_non_empty(ordered_rows, "business_name"),
                trade_name=_latest_non_empty(ordered_rows, "trade_name"),
                legal_form=_latest_non_empty(ordered_rows, "legal_form"),
                subject_status=_latest_non_empty(ordered_rows, "subject_status"),
                registration_date=registration_date,
                registration_year=registration_date.year if registration_date is not None else None,
                city=_latest_non_empty(ordered_rows, "city"),
                has_red_flags=representative.has_red_flags,
                has_activity_text=any(bool(row.activity_text and row.activity_text.strip()) for row in company_rows),
                has_ownership_text=any(bool(row.ownership_text and row.ownership_text.strip()) for row in company_rows),
                search_window_start=min((row.search_date_from for row in company_rows if row.search_date_from is not None), default=None),
                search_window_end=max((row.search_date_to for row in company_rows if row.search_date_to is not None), default=None),
            )
        )

    return features, skipped


def _build_joined_features(inputs: _FeatureInputs) -> tuple[list[JoinedCompanyFeature], int]:
    skipped = 0
    materialized_at = utc_now_naive()
    features: list[JoinedCompanyFeature] = []

    for company_nipt, app_feature in inputs.app.items():
        qkb_feature = inputs.qkb.get(company_nipt)
        if qkb_feature is None:
            skipped += 1
            continue

        assessment = assess_app_qkb_join(company_nipt, qkb_feature.company_nipt)
        if assessment.status != "safe":
            skipped += 1
            continue

        features.append(
            JoinedCompanyFeature(
                company_nipt=company_nipt,
                materialized_at=materialized_at,
                app_source_row_count=app_feature.source_row_count,
                app_source_snapshot_count=app_feature.source_snapshot_count,
                app_structured_record_ids=app_feature.source_structured_record_ids,
                qkb_source_row_count=qkb_feature.source_row_count,
                qkb_source_snapshot_count=qkb_feature.source_snapshot_count,
                qkb_structured_record_ids=qkb_feature.source_structured_record_ids,
                exact_join_match=True,
                business_name=qkb_feature.business_name,
                legal_form=qkb_feature.legal_form,
                subject_status=qkb_feature.subject_status,
                city=qkb_feature.city,
                registration_date=qkb_feature.registration_date,
                first_procurement_date=app_feature.first_procurement_date,
                last_procurement_date=app_feature.last_procurement_date,
                company_age_days_at_first_procurement=_date_diff_days(
                    qkb_feature.registration_date,
                    app_feature.first_procurement_date,
                ),
                company_age_days_at_last_procurement=_date_diff_days(
                    qkb_feature.registration_date,
                    app_feature.last_procurement_date,
                ),
                total_budget_limit_amount=app_feature.total_budget_limit_amount,
                total_winner_value_amount=app_feature.total_winner_value_amount,
                cancelled_procurement_count=app_feature.cancelled_procurement_count,
                suspended_procurement_count=app_feature.suspended_procurement_count,
                has_red_flags=qkb_feature.has_red_flags,
            )
        )

    return features, skipped


def materialize_app_features(db: Session) -> dict[str, Any]:
    source_rows = db.scalars(
        exclude_corrupted_raw_fetches(
            select(NormalizedAppExportRow).order_by(NormalizedAppExportRow.id),
            NormalizedAppExportRow,
        )
    ).all()
    stats = _base_stats("app_company_features", len(source_rows))
    features, skipped = _build_app_features(source_rows)

    delete_result = db.execute(delete(AppCompanyFeature))
    db.add_all(features)
    db.commit()

    stats["rows_deleted_before_insert"] = delete_result.rowcount or 0
    stats["rows_inserted"] = len(features)
    stats["rows_materialized"] = len(features)
    stats["groups_skipped"] = skipped
    return stats


def materialize_qkb_features(db: Session) -> dict[str, Any]:
    source_rows = db.scalars(
        exclude_corrupted_raw_fetches(
            select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.id),
            NormalizedQkbSearchRow,
        )
    ).all()
    stats = _base_stats("qkb_company_features", len(source_rows))
    features, skipped = _build_qkb_features(source_rows)

    delete_result = db.execute(delete(QkbCompanyFeature))
    db.add_all(features)
    db.commit()

    stats["rows_deleted_before_insert"] = delete_result.rowcount or 0
    stats["rows_inserted"] = len(features)
    stats["rows_materialized"] = len(features)
    stats["groups_skipped"] = skipped
    return stats


def materialize_joined_features(db: Session) -> dict[str, Any]:
    app_rows = db.scalars(
        exclude_corrupted_raw_fetches(
            select(NormalizedAppExportRow).order_by(NormalizedAppExportRow.id),
            NormalizedAppExportRow,
        )
    ).all()
    qkb_rows = db.scalars(
        exclude_corrupted_raw_fetches(
            select(NormalizedQkbSearchRow).order_by(NormalizedQkbSearchRow.id),
            NormalizedQkbSearchRow,
        )
    ).all()
    stats = _base_stats("joined_company_features", len(app_rows) + len(qkb_rows))
    app_features, app_skipped = _build_app_features(app_rows)
    qkb_features, qkb_skipped = _build_qkb_features(qkb_rows)
    joined_features, join_skipped = _build_joined_features(
        _FeatureInputs(
            app={feature.company_nipt: feature for feature in app_features},
            qkb={feature.company_nipt: feature for feature in qkb_features},
        )
    )

    delete_result = db.execute(delete(JoinedCompanyFeature))
    db.add_all(joined_features)
    db.commit()

    stats["rows_deleted_before_insert"] = delete_result.rowcount or 0
    stats["rows_inserted"] = len(joined_features)
    stats["rows_materialized"] = len(joined_features)
    stats["groups_skipped"] = app_skipped + qkb_skipped + join_skipped
    return stats


def materialize_all_features(db: Session) -> dict[str, Any]:
    return {
        "app": materialize_app_features(db),
        "qkb": materialize_qkb_features(db),
        "joined": materialize_joined_features(db),
    }
