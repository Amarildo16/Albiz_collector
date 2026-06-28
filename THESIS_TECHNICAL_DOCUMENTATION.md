# Thesis Technical Documentation

## Purpose

Albiz Collector is a data collection and preparation system built for a university thesis on Albanian business dynamics. Its purpose is to collect public procurement and company-registry data, preserve source evidence, normalize the data into relational datasets, and create company-level analytical features for later statistical or machine-learning work.

The system is not an end-user application. It is a reproducible research pipeline that prioritizes provenance, rerunnable transformations, and conservative joins.

## Why The System Was Built

The thesis requires a structured dataset that connects public procurement activity with company registry context. The source data is available through public web interfaces and export files, but it is not directly ready for analysis. Albiz Collector was built to:

- keep raw source artifacts for traceability;
- store source snapshots in a database;
- normalize APP and QKB records into explicit tables;
- build feature tables at company level;
- profile coverage, missingness, and joinability;
- support later business dynamics analysis without relying on manual spreadsheet assembly.

## Data Sources Used

### APP Procurement Exports

The APP source is the Albanian Public Procurement Agency export page and yearly CSV export endpoint. The collector downloads the export index and selected yearly CSV files. Each CSV file is saved as a raw artifact and represented as a structured snapshot.

Implemented command:

```powershell
python -m albiz_collector.cli run app-exports
```

### QKB Search Collection

The QKB source is the public subject-search page. The implemented collector uses HTTP requests, not Playwright, for the supported workflow. It can search by exact NIPT or by registration date range. Date-range runs without a NIPT are split into daily requests and tracked in `qkb_search_runs` so interrupted runs can resume.

Implemented command examples:

```powershell
python -m albiz_collector.cli run qkb-search --nipt M21528028T
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --forme-ligjore SHPK
```

### QKB Targeted NIPT Lookup

The targeted QKB lookup command is designed for bounded enrichment of known identifiers. It accepts one exact NIPT or a UTF-8 text file with one NIPT per line. It persists raw pages, upserts structured snapshots, and immediately materializes normalized QKB rows for successful lookups.

Implemented command examples:

```powershell
python -m albiz_collector.cli run qkb-search-by-nipt --nipt M21528028T
python -m albiz_collector.cli run qkb-search-by-nipt --input .\nipts.txt --limit 100 --delay-seconds 1
```

### OpenCorporates Financial Enrichment

OpenCorporates enrichment is implemented as a bounded, rate-limited secondary enrichment path. It selects NIPT values from normalized QKB rows, fetches public OpenCorporates company profile pages, and stores HTML-derived financial indicators and yearly revenue/profit values where they are visible.

Implemented command:

```powershell
python -m albiz_collector.cli run opencorporates-financials --limit 100 --delay-seconds 1
```

This enrichment should be treated as supplementary. It does not replace official financial statements and does not parse QKB PDFs.

## Pipeline Architecture

The pipeline has four main layers:

```text
raw source data
  -> raw_fetches + raw files
  -> structured_records
  -> normalized tables
  -> feature tables and profiling outputs
```

### Raw Layer

Raw source responses are written to disk under `RAW_STORAGE_DIR` and registered in `raw_fetches`. Each raw fetch stores source name, URL, fetch kind, status code, content type, SHA-256 content hash, storage path, optional metadata, and corruption/quarantine fields.

### Structured Snapshot Layer

`structured_records` stores one latest structured snapshot per logical external key. APP uses one snapshot per export year. QKB search uses snapshots for exact NIPT searches, date windows, legal-form/date chunks, and targeted NIPT lookups.

### Normalized Layer

The normalized layer converts source-specific snapshots into relational rows:

- `normalized_app_export_rows`
- `normalized_qkb_search_rows`

Normalization skips quarantined raw fetches and can be rerun safely. APP normalization parses CSV rows. QKB normalization extracts fields from parsed search result payloads.

### Feature Layer

The feature layer aggregates normalized rows into company-level analytical tables:

- `app_company_features`
- `qkb_company_features`
- `joined_company_features`

The joined feature table uses exact NIPT equality only. It joins APP `winner_nipt` to QKB `business_nipt`; fuzzy or name-only joins are intentionally not used.

## Database Structure At A High Level

Core tables:

- `raw_fetches`: raw artifact provenance and integrity metadata.
- `structured_records`: source snapshots keyed by source, record type, and external key.
- `qkb_search_runs`: resumable QKB date-range run state.

Normalized tables:

- `normalized_app_export_rows`: procurement rows from APP CSV exports.
- `normalized_qkb_search_rows`: business rows from QKB search responses.

Feature tables:

- `app_company_features`: procurement-side company aggregates by APP winner NIPT.
- `qkb_company_features`: registry-side company features by QKB business NIPT.
- `joined_company_features`: exact APP/QKB joined company features.

OpenCorporates enrichment tables:

- `opencorporates_company_profiles`: one latest fetched profile per NIPT.
- `opencorporates_financial_years`: one annual financial record per NIPT/year/source type.

## Normalized Datasets

`normalized_app_export_rows` includes procurement reference, contracting authority, procurement subject, procedure type, contract type, publication/opening/closing dates, cancellation/suspension flags, budget amount, winner name, winner NIPT, winner value, CPV codes, and the original source payload.

`normalized_qkb_search_rows` includes search context, business NIPT, business name, trade name, legal form, registration date, city, ownership text, subject status, subject type, activity text, administrator/shareholder text, red-flag indicator, and the original source payload.

## Feature Datasets

`app_company_features` supports procurement exposure and outcome analysis, including row counts, active/cancelled/suspended procurement counts, value totals, budget-to-award ratios, concentration metrics, year-over-year changes, and support counts.

`qkb_company_features` supports registry context, including business identity, legal form, subject status, registration date/year, city, red-flag indicator, and activity/ownership text presence.

`joined_company_features` combines APP and QKB features for companies where exact NIPT matches exist. It includes company age at first and last observed procurement where dates are available.

## Profiling And Audit Outputs

Profiling commands report row counts, missingness, identifier coverage, exact join coverage, feature sparsity, readiness status, and QKB legal-form distribution.

Audit commands inspect raw fetch integrity and QKB search run state. The raw-fetch audit can detect missing files and content-hash mismatches, and can mark affected rows as corrupted when explicitly requested.

Smoke checks are live source-contract checks for APP exports and QKB search. They are low-volume and do not write database rows.

## Support For Business Dynamics Analysis

The implemented dataset supports analyses such as:

- procurement participation over time by company;
- procurement value and budget concentration;
- cancellation and suspension patterns;
- company age at procurement activity;
- registry status and legal form context;
- exact-match joined analysis where APP and QKB identifiers align;
- exploratory financial enrichment for companies with visible OpenCorporates data.

The collector prepares the data for later statistical or ML workflows. It does not train models or define prediction labels.

## Current Limitations

- QKB date-range searches may be truncated when a daily search returns the source-side result cap.
- QKB coverage is limited to the searches actually run; there is no implemented full QKB Universe collector.
- APP company-level aggregation depends on usable winner NIPT values. Rows without exactly one recognizable NIPT remain APP-only rows.
- The joined dataset uses exact NIPT equality only. This is conservative but leaves unmatched rows when identifiers are missing or inconsistent.
- OpenCorporates enrichment is HTML-derived and coverage is opportunistic.
- No batch QKB document collection, QKB historical extract parsing, QKB PDF text extraction, or QKB financial PDF extraction is part of the current thesis implementation.
- Public source pages can change structure, which may require collector or parser maintenance.
