# Research Dataset Design

This note defines the current thesis-oriented analytical dataset design built on top of the repo's raw, structured, and normalized layers.

## Source datasets

### APP dataset

- Table: `normalized_app_export_rows`
- Analytical unit: one procurement row from one APP export CSV
- Main use: procurement exposure, award context, and procurement outcome/value analysis

Strong fields:
- `procurement_reference`
- `winner_nipt`
- `publication_date`
- `budget_limit_amount`
- `winner_value_amount`
- `procedure_type`
- `contract_type`
- `is_cancelled`
- `is_suspended`

Useful with caution:
- `winner_name`
- `procurement_subject`
- `cpv_codes`

Weak/noisy:
- free-text row payload content outside the normalized columns

### QKB dataset

- Table: `normalized_qkb_search_rows`
- Analytical unit: one business result row from one QKB search snapshot
- Main use: company identity, registry status, legal form, timing, and registry context

Strong fields:
- `business_nipt`
- `business_name`
- `legal_form`
- `registration_date`
- `subject_status`

Useful with caution:
- `trade_name`
- `ownership_text`
- `activity_text`
- `has_red_flags`

Weak/noisy:
- `administrators_text`
- `subject_type` when sparsely populated
- search-form context fields as intrinsic company attributes

## Recommended analytical design

Keep two source datasets first:

1. APP procurement rows
2. QKB registry rows

Then derive a joined analytical dataset only where an exact company identifier exists.

### Primary entities

- Procurement event / procurement row
- Registry business row
- Exact APP award-to-business join row when identifiers permit

### Safest default join

- APP `winner_nipt` -> QKB `business_nipt`
- Match type: exact only

This is the minimum defensible automated join currently supported by the repo.

## Join policy

### Safe joins

- Exact `winner_nipt == business_nipt`

### Possible but risky joins

- Winner name vs business name for manual review only
- Trade-name comparisons as secondary human review context

### Joins to avoid by default

- Automatic name-only joins
- Address or city joins
- Activity-text joins
- Contracting-authority text joins to registry business rows

If an APP row lacks `winner_nipt`, keep it in the APP-only dataset unless a later manual review workflow is introduced explicitly.

## Feature candidates for later work

These are candidates only, not implemented feature pipelines.

### Company identity / registry features

- `business_nipt`
- `legal_form`
- `registration_date`
- derived business age from `registration_date`
- `subject_status`
- `ownership_text`

### Procurement participation / exposure features

- count of APP rows by `winner_nipt`
- sum of `winner_value_amount` by `winner_nipt`
- sum of `budget_limit_amount` by `winner_nipt`
- APP row counts by `procedure_type`
- APP row counts by `contract_type`

### Procurement outcome / value features

- budget-to-award ratio where both amounts exist
- cancellation rate by winner or authority context
- suspension rate by winner or authority context
- award value distribution by company

### Temporal features

- publication year / month
- company age at procurement publication date
- procurement cadence over time by company

### Risk-oriented candidates

- QKB `has_red_flags`
- QKB `subject_status`
- repeated APP cancellations involving the same winner context
- repeated APP suspensions involving the same winner context

## Research-safe vs research-risky usage

### Safe and defensible

- Exact NIPT joins
- Registry identity fields
- Procurement value/date/procedure fields
- Provenance-backed aggregation by normalized rows

### Usable with caution

- Name-based manual review support
- Ownership text as a grouped explanatory field
- Activity text as a coarse thematic field
- QKB red-flag boolean as a registry presentation signal rather than a final risk label

### Too weak for default automated use

- Fuzzy company matching without exact NIPT
- Administrator-name joins
- City-only or address-like joins
- Treating free-text activity descriptions as stable categories without further coding

## Minimum defensible thesis dataset

If the thesis needs a conservative first analytical dataset, use:

1. `normalized_app_export_rows`
2. `normalized_qkb_search_rows`
3. a joined subset where `winner_nipt == business_nipt`

That design keeps provenance visible, avoids weak matching, and stays close to the current repo data quality.