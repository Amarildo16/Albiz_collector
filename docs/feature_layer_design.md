# Feature Layer Design

The feature layer is a rerunnable analytical layer built from normalized APP and QKB datasets.

## Commands

```powershell
python -m albiz_collector.cli features app
python -m albiz_collector.cli features qkb
python -m albiz_collector.cli features joined
python -m albiz_collector.cli features all
```

Each command rebuilds its target feature table from normalized rows.

## `app_company_features`

Unit: one exact APP `winner_nipt`.

Source: `normalized_app_export_rows`.

Rows without a valid winner NIPT are excluded.

Implemented feature groups:

- source row and snapshot counts;
- first and last procurement dates and years;
- active year span;
- active, cancelled, and suspended procurement counts;
- cancellation and suspension rates;
- budget and winner-value totals;
- active and cancelled value subtotals;
- safe winner-to-positive-budget ratios;
- near-budget and over-budget indicators;
- purchase-ticket counts and values;
- zero-budget-with-winner-value checks;
- distinct authority, procedure type, and contract type counts;
- top authority and procedure concentration;
- year-over-year value and contract-count jump indicators;
- support counts for rows with winner value, budget, and valid ratios.

## `qkb_company_features`

Unit: one exact QKB `business_nipt`.

Source: `normalized_qkb_search_rows`.

Implemented feature groups:

- source row and snapshot counts;
- representative business name and trade name;
- legal form;
- subject status;
- registration date and year;
- city;
- red-flag indicator;
- activity-text and ownership-text presence;
- search-window context.

## `joined_company_features`

Unit: one company present in both APP and QKB feature inputs.

Join rule:

```text
app_company_features.company_nipt == qkb_company_features.company_nipt
```

Implemented feature groups:

- exact-join indicator;
- source row, snapshot, and structured-record provenance;
- APP procurement aggregates copied from `app_company_features`;
- QKB registry context copied from `qkb_company_features`;
- company age in days at first and last observed procurement where dates are available.

## Feature Confidence

`src/albiz_collector/features/registry.py` classifies features as:

- `safe`
- `caution`
- `not_recommended`

Profiling uses this registry to report feature sparsity and readiness. A `caution` feature is still implemented, but should be interpreted with more care in thesis analysis.
