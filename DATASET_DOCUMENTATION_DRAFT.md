# Dataset Documentation Draft

## Dataset Purpose

This dataset supports thesis analysis of Albanian business dynamics by combining public procurement records with company registry context and selected financial enrichment. The dataset is built by Albiz Collector from public sources and stored in a relational database with raw artifact provenance.

## Source Datasets

### APP Procurement Exports

- Source: Albanian Public Procurement Agency export page and yearly CSV downloads.
- Collector: `run app-exports`.
- Raw artifacts: export index HTML and yearly CSV files.
- Structured snapshot type: `procurement_export_year`.
- Normalized table: `normalized_app_export_rows`.

### QKB Subject Search

- Source: QKB public subject-search page.
- Collector: `run qkb-search`.
- Modes: exact NIPT search, date-range search, optional legal-form filter.
- Raw artifacts: QKB search result HTML pages.
- Structured snapshot type: `qkb_search_snapshot`.
- Normalized table: `normalized_qkb_search_rows`.

### QKB Targeted NIPT Lookup

- Source: same QKB public subject-search endpoint.
- Collector: `run qkb-search-by-nipt`.
- Purpose: bounded backfill for known company identifiers.
- Input: one NIPT or UTF-8 file with one NIPT per line.
- Output: raw QKB pages, structured snapshots, and normalized QKB rows.

### OpenCorporates Financial Enrichment

- Source: public OpenCorporates company profile pages.
- Collector: `run opencorporates-financials`.
- Purpose: secondary financial enrichment where public profile pages expose relevant data.
- Tables:
  - `opencorporates_company_profiles`
  - `opencorporates_financial_years`

OpenCorporates enrichment is supplementary and does not replace official financial filings.

## Main Tables

### Provenance And Snapshot Tables

- `raw_fetches`: metadata for raw files, including source, URL, fetch kind, content hash, storage path, fetch time, and corruption flags.
- `structured_records`: latest structured source snapshot per source/record/external key.
- `qkb_search_runs`: resumable QKB date-range run state.

### Normalized Tables

- `normalized_app_export_rows`: one procurement row from an APP export CSV.
- `normalized_qkb_search_rows`: one business result row from a QKB search snapshot.

### Feature Tables

- `app_company_features`: company-level procurement features by APP winner NIPT.
- `qkb_company_features`: company-level registry features by QKB business NIPT.
- `joined_company_features`: exact APP/QKB joins where APP `winner_nipt` equals QKB `business_nipt`.

### OpenCorporates Tables

- `opencorporates_company_profiles`: one latest profile row per NIPT.
- `opencorporates_financial_years`: annual revenue/profit values where parsed from visible OpenCorporates profile data.

## Key Identifiers

- `NIPT` / `NUIS`: primary company identifier used for exact joins.
- APP identifier fields:
  - `winner_nipt`
  - `winner_name`
  - `procurement_reference`
- QKB identifier fields:
  - `business_nipt`
  - `business_name`
  - `trade_name`
- OpenCorporates identifier field:
  - `nipt`

The default join policy is exact identifier equality only:

```text
normalized_app_export_rows.winner_nipt == normalized_qkb_search_rows.business_nipt
```

Name-only, fuzzy, address, city, activity-text, or administrator-name joins are not part of the implemented dataset.

## Raw Data Handling

Raw source responses are written under `RAW_STORAGE_DIR`. Each file is registered in `raw_fetches` with a SHA-256 content hash. This provides traceability from normalized rows back to raw source artifacts.

Raw-fetch integrity can be checked with:

```powershell
python -m albiz_collector.cli audit raw-fetches
```

Rows can be explicitly quarantined with `--mark-corrupted` when files are missing or hashes no longer match. Normalization and profiling avoid corrupted raw artifacts.

## Normalized Data

### `normalized_app_export_rows`

Important fields:

- `export_year`
- `procurement_reference`
- `contracting_authority`
- `procurement_subject`
- `procedure_type`
- `contract_type`
- `publication_date`
- `opening_date`
- `closing_date`
- `is_cancelled`
- `is_suspended`
- `budget_limit_amount`
- `winner_name`
- `winner_nipt`
- `winner_value_amount`
- `cpv_codes`
- `source_payload`

APP winner NIPT normalization keeps a company identifier only when exactly one NIPT-like value is detected.

### `normalized_qkb_search_rows`

Important fields:

- `search_nipt`
- `search_date_from`
- `search_date_to`
- `business_nipt`
- `business_name`
- `trade_name`
- `legal_form`
- `registration_date`
- `city`
- `ownership_text`
- `subject_status`
- `subject_type`
- `activity_text`
- `administrators_text`
- `has_red_flags`
- `source_payload`

## Feature Tables

### `app_company_features`

Unit: one APP winner NIPT.

Feature groups include:

- procurement participation counts;
- active, cancelled, and suspended procurement counts and rates;
- budget and winner-value totals;
- safe winner-to-budget ratios;
- budget proximity indicators;
- purchase-ticket exposure;
- contracting-authority and procedure concentration;
- year-over-year value and contract-count changes;
- support counts for non-missing value fields.

Rows without a valid `winner_nipt` are excluded from APP company features.

### `qkb_company_features`

Unit: one QKB business NIPT.

Feature groups include:

- business name and trade name;
- legal form;
- subject status;
- registration date and year;
- city;
- red-flag indicator;
- presence indicators for activity and ownership text;
- source search-window context.

### `joined_company_features`

Unit: one company with exact APP and QKB feature matches.

The table copies APP procurement features, QKB registry features, and adds age-at-procurement fields where registration and procurement dates are available.

## Known Data Quality Checks

Implemented checks and profiling outputs include:

- raw file existence and content-hash verification;
- raw-fetch corruption quarantine;
- APP winner NIPT coverage;
- QKB business NIPT coverage;
- important field missingness for normalized APP and QKB tables;
- exact APP/QKB join coverage;
- feature sparsity by feature table;
- feature readiness summaries;
- QKB legal-form distribution;
- live source-contract smoke checks for APP and QKB search.

Relevant commands:

```powershell
python -m albiz_collector.cli profile normalized
python -m albiz_collector.cli profile features
python -m albiz_collector.cli profile all
python -m albiz_collector.cli profile qkb-legal-forms
python -m albiz_collector.cli smoke all
```

## Known Limitations

- The dataset includes only data that has been collected locally; it is not automatically a complete national business universe.
- QKB date-range searches can be incomplete when the source returns a capped result set.
- APP rows without a single clear winner NIPT cannot enter company-level APP features or exact APP/QKB joins.
- QKB free-text fields are retained but should be used cautiously.
- OpenCorporates financial enrichment is secondary, HTML-derived, and may have limited coverage.
- No implemented workflow extracts QKB historical extract PDFs, parses QKB document batches, or derives financial data from PDFs.
- Public source pages may change, requiring parser or collector updates.
