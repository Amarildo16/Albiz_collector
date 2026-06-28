# Data Profiling And Analytical Readiness

The profiling layer measures the current local database state. It is read-only.

## Commands

```powershell
python -m albiz_collector.cli profile normalized
python -m albiz_collector.cli profile features
python -m albiz_collector.cli profile all
python -m albiz_collector.cli profile qkb-legal-forms
```

## Normalized Profiling

`profile normalized` reports:

- row counts for `normalized_app_export_rows` and `normalized_qkb_search_rows`;
- APP winner NIPT coverage;
- QKB business NIPT coverage;
- important APP field missingness;
- important QKB field missingness;
- exact APP/QKB join coverage.

## Feature Profiling

`profile features` reports:

- row counts for `app_company_features`, `qkb_company_features`, and `joined_company_features`;
- feature sparsity using the feature registry;
- readiness status for each feature table.

## Combined Profiling

`profile all` combines normalized and feature profiling and adds an analytical-readiness summary:

- strengths visible in the current dataset;
- weaknesses;
- blockers;
- currently usable feature families;
- priority backfill actions.

## QKB Legal-Form Profiling

`profile qkb-legal-forms` reports:

- total normalized QKB rows;
- distinct business NIPTs;
- missing legal-form count;
- SHPK and non-SHPK counts;
- raw legal-form distributions;
- canonical legal-form distributions.

This is useful for checking whether QKB collection aligns with the intended company cohorts.

## Scope Limits

Profiling does not collect new data, update rows, create labels, or train models. It reports the analytical readiness of the data already present in the local database.
