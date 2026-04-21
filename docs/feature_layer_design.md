# Feature Layer Design

This note defines the baseline analytical feature layer built on top of the normalized APP and QKB datasets.

## Purpose

The feature layer is a small research-oriented convenience layer for later exploratory analysis and model preparation.

It does not replace raw, structured, or normalized storage.

## Feature tables

### `app_company_features`

- Unit: one exact winner NIPT aggregated from APP rows
- Source: `normalized_app_export_rows`
- Strong features:
  - `source_row_count`
  - `first_procurement_date`
  - `last_procurement_date`
  - `total_budget_limit_amount`
  - `total_winner_value_amount`
  - `cancelled_procurement_count`
  - `suspended_procurement_count`
  - `distinct_contracting_authority_count`
- Caution-level features:
  - `has_small_value_procedures`
  - `has_open_local_procedures`
  - `latest_winner_name`

Rows without `winner_nipt` are excluded from company-level APP features.

### `qkb_company_features`

- Unit: one exact business NIPT represented from QKB search rows
- Source: `normalized_qkb_search_rows`
- Strong features:
  - `business_name`
  - `legal_form`
  - `subject_status`
  - `registration_date`
  - `registration_year`
- Caution-level features:
  - `city`
  - `has_red_flags`
  - `has_activity_text`
  - `has_ownership_text`

### `joined_company_features`

- Unit: one company present in both APP company features and QKB company features
- Join rule: exact `winner_nipt == business_nipt` only
- Strong features:
  - `exact_join_match`
  - `legal_form`
  - `subject_status`
  - `company_age_days_at_first_procurement`
  - `company_age_days_at_last_procurement`
  - APP-side totals and counts copied from `app_company_features`
- Caution-level features:
  - `city`
  - `has_red_flags`

## Provenance

Each feature table keeps:

- source row counts
- source snapshot counts
- source structured-record id lists

This keeps the feature layer traceable back to normalized source snapshots without introducing a larger warehouse design.

## Rerun behavior

Feature materialization is deterministic and rerunnable.

Each feature command replaces the current feature table contents and rebuilds them from normalized data.

## Commands

- `python -m albiz_collector.cli features app`
- `python -m albiz_collector.cli features qkb`
- `python -m albiz_collector.cli features joined`
- `python -m albiz_collector.cli features all`