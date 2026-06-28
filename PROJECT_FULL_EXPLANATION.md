# Project Full Explanation

## Scope

Albiz Collector is a Python research pipeline for collecting and preparing Albanian business data for thesis analysis. The active implementation covers APP procurement exports, QKB subject search, targeted QKB NIPT lookup, OpenCorporates financial enrichment, normalization, feature materialization, profiling, audits, smoke checks, and scheduling.

The active implementation does not include QKB Universe collection, batch QKB document extraction, historical extract PDF parsing, QKB PDF text extraction, or QKB financial-document extraction.

## Architecture

The repository follows a layered data pipeline:

```text
collectors
  -> raw_fetches + raw files
  -> structured_records
  -> normalized tables
  -> feature tables
  -> profiling and audit summaries
```

Important modules:

- `src/albiz_collector/cli.py`: Typer CLI command surface.
- `src/albiz_collector/config.py`: environment-driven runtime settings.
- `src/albiz_collector/models.py`: SQLAlchemy table models.
- `src/albiz_collector/sources/`: source collectors and enrichers.
- `src/albiz_collector/normalization/`: raw/structured to normalized materialization.
- `src/albiz_collector/features/`: company-level feature materialization.
- `src/albiz_collector/profiling/`: analytical readiness summaries.
- `src/albiz_collector/audit/`: raw-fetch and QKB run-state inspection.
- `src/albiz_collector/smoke/`: live source-contract checks.
- `src/albiz_collector/scheduler.py`: scheduled APP and QKB collection.
- `alembic/versions/`: versioned schema migrations.

## Implemented Sources

### APP Exports

The APP collector downloads the procurement export index and yearly CSV files. It persists raw HTML/CSV artifacts and upserts one structured record per export year.

Main command:

```powershell
python -m albiz_collector.cli run app-exports
```

### QKB Search

The QKB search collector uses HTTP requests against the public subject-search page. It supports exact NIPT searches and registration date-range searches. Date-range searches without NIPT are split into daily requests and tracked in `qkb_search_runs` for resumability.

Main commands:

```powershell
python -m albiz_collector.cli run qkb-search --nipt M21528028T
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --forme-ligjore SHPK
```

### QKB Targeted NIPT Lookup

The targeted lookup command performs bounded exact-NIPT QKB lookups from one NIPT or an input file. It persists raw pages, structured snapshots, and normalized rows.

Main commands:

```powershell
python -m albiz_collector.cli run qkb-search-by-nipt --nipt M21528028T
python -m albiz_collector.cli run qkb-search-by-nipt --input .\nipts.txt --limit 100 --delay-seconds 1
```

### OpenCorporates Financial Enrichment

The OpenCorporates command fetches public profile pages for selected NIPTs and stores profile-level and yearly financial values where visible.

Main command:

```powershell
python -m albiz_collector.cli run opencorporates-financials --limit 100 --delay-seconds 1
```

This enrichment is secondary and HTML-derived. It is not a substitute for official financial statement extraction.

## Storage Model

`raw_fetches` records source provenance and integrity metadata for each saved artifact. Raw files are stored on disk under `RAW_STORAGE_DIR`.

`structured_records` stores a latest structured snapshot per source, record type, and external key. It keeps payload data close to the source shape while making later materialization deterministic.

`qkb_search_runs` stores resumable state for QKB date-range runs.

## Normalization

Normalization creates relational source-specific tables:

- `normalized_app_export_rows`
- `normalized_qkb_search_rows`

APP normalization parses CSV rows and extracts procurement fields, amounts, dates, status flags, and winner NIPT. QKB normalization converts parsed search response records into company registry rows.

Commands:

```powershell
python -m albiz_collector.cli normalize app-exports
python -m albiz_collector.cli normalize qkb-search
python -m albiz_collector.cli normalize all
```

## Feature Materialization

The feature layer builds company-level tables:

- `app_company_features`
- `qkb_company_features`
- `joined_company_features`

The joined table is built only from exact NIPT matches. No fuzzy matching is implemented.

Commands:

```powershell
python -m albiz_collector.cli features app
python -m albiz_collector.cli features qkb
python -m albiz_collector.cli features joined
python -m albiz_collector.cli features all
```

## Profiling, Audits, And Smoke Checks

Profiling reports normalized row counts, field missingness, identifier coverage, exact join coverage, feature sparsity, and readiness summaries.

Audit commands inspect raw-fetch integrity and QKB search run state. Raw-fetch auditing can mark missing or hash-mismatched artifacts as corrupted when explicitly requested.

Smoke checks are live, low-volume checks for APP export and QKB search page contracts.

Commands:

```powershell
python -m albiz_collector.cli profile all
python -m albiz_collector.cli audit raw-fetches
python -m albiz_collector.cli audit qkb-search-runs
python -m albiz_collector.cli smoke all
```

## Scheduler

The scheduler runs APP export collection and, when enabled, QKB search over a rolling lookback window. QKB scheduler dates are calculated in `Europe/Tirane`.

Command:

```powershell
python -m albiz_collector.cli scheduler
```

## Experimental Area

The CLI includes an `experimental` group. These commands are not part of the supported thesis workflow:

- `experimental qkb-notices`
- `experimental qkb-document-fetch-one`
- `experimental qkb-legal-form-chunk-probe`
- `experimental qkb-secondary-chunk-probe`
- `experimental opencorporates-financial-discovery`

The one-NIPT QKB document fetcher is a bounded probe only. There is no active batch document collector, QKB historical extract parser, PDF text pipeline, or QKB financial-document extractor.

## Main Limitations

- QKB source search results can be capped, so broad date-range coverage can be incomplete.
- The dataset is limited to what has been collected locally.
- APP rows without exactly one clear winner NIPT cannot enter exact joined company features.
- OpenCorporates enrichment depends on visible public profile data and may be sparse.
- Public source page structures may change.
