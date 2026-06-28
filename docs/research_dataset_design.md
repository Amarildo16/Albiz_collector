# Research Dataset Design

This note defines the thesis-oriented analytical dataset design implemented in the current repository.

## Source Datasets

### APP Procurement Rows

- Table: `normalized_app_export_rows`
- Unit: one procurement row from one APP export CSV.
- Main use: procurement participation, award values, procedure context, cancellation/suspension status, and company-level procurement exposure.

Core fields:

- `procurement_reference`
- `contracting_authority`
- `procedure_type`
- `contract_type`
- `publication_date`
- `is_cancelled`
- `is_suspended`
- `budget_limit_amount`
- `winner_name`
- `winner_nipt`
- `winner_value_amount`

### QKB Registry Rows

- Table: `normalized_qkb_search_rows`
- Unit: one business result row from one QKB search snapshot.
- Main use: company identity, registry status, legal form, registration timing, and context for exact APP joins.

Core fields:

- `business_nipt`
- `business_name`
- `trade_name`
- `legal_form`
- `registration_date`
- `city`
- `subject_status`
- `activity_text`
- `has_red_flags`

### OpenCorporates Financial Enrichment

- Tables: `opencorporates_company_profiles`, `opencorporates_financial_years`
- Unit: one profile per NIPT and one annual financial row per NIPT/year/source type.
- Main use: supplementary revenue/profit context where visible on public profile pages.

This enrichment is not required for the APP/QKB joined feature layer.

## Join Policy

The implemented join policy is exact identifier equality:

```text
APP winner_nipt == QKB business_nipt
```

This is the only automated join used by the feature layer.

Avoid by default:

- automatic name-only joins;
- fuzzy company-name matching;
- address or city joins;
- activity-text joins;
- administrator-name joins.

Rows without exact identifiers remain in their source dataset.

## Implemented Analytical Tables

### `app_company_features`

Unit: one APP winner NIPT.

Main feature groups:

- procurement counts;
- cancellation and suspension rates;
- budget and winner-value totals;
- safe winner-to-budget ratios;
- budget proximity indicators;
- procedure and authority concentration;
- year-over-year value and count changes.

### `qkb_company_features`

Unit: one QKB business NIPT.

Main feature groups:

- registry identity;
- legal form;
- subject status;
- registration date and year;
- city;
- red-flag indicator;
- activity and ownership text presence.

### `joined_company_features`

Unit: one exact APP/QKB joined company NIPT.

Main feature groups:

- APP procurement aggregates;
- QKB registry enrichment;
- company age at first and last observed procurement;
- exact-join provenance fields.

## Research-Safe Usage

Safe and defensible:

- exact NIPT joins;
- procurement dates, values, procedure types, and status flags;
- QKB legal form, registration date, and subject status;
- provenance-backed aggregation by normalized row.

Use with caution:

- QKB free-text activity and ownership fields;
- APP winner names as labels or explanatory text;
- QKB red-flag indicator as a source-side signal, not a final risk label;
- OpenCorporates financial enrichment due to coverage variability.

Not implemented:

- QKB Universe collection;
- QKB document batch extraction;
- QKB historical extract parsing;
- QKB PDF text extraction;
- QKB financial-document extraction.
