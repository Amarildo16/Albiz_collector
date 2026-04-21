# Data Profiling And Analytical Readiness

This note defines the small profiling layer for the current normalized and feature datasets.

## Purpose

The profiling commands measure the current local dataset honestly.

They answer questions such as:

- how many normalized APP and QKB rows currently exist
- how many feature rows currently exist
- how often important fields are missing
- how much exact APP to QKB join coverage is currently available
- which feature tables are usable now and which are blocked by missing data or missing joins

## Commands

- `python -m albiz_collector.cli profile normalized`
- `python -m albiz_collector.cli profile features`
- `python -m albiz_collector.cli profile all`

## What is measured

### Normalized datasets

- row counts for `normalized_app_export_rows` and `normalized_qkb_search_rows`
- missingness for important APP and QKB fields
- APP winner NIPT coverage
- QKB business NIPT coverage
- distinct identifier counts
- exact APP `winner_nipt` to QKB `business_nipt` join coverage

### Feature datasets

- row counts for `app_company_features`, `qkb_company_features`, and `joined_company_features`
- feature sparsity for important fields using the current feature-confidence registry
- a small readiness assessment for each feature table

### Analytical readiness summary

- strengths visible in the current local dataset
- weaknesses and blockers
- usable feature families now
- recommended backfill actions that would most improve downstream analysis

## Scope limits

The profiling layer is read-only.

It does not add new data, create labels, or redesign the feature layer. It only measures what the current local dataset can realistically support.