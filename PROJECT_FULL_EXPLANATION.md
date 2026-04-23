# Project Full Explanation

## 1. Executive Summary

This repository is a Python data-collection and materialization pipeline for two Albanian public-data domains:

- APP public procurement export data from `app.gov.al`
- QKB business-registry search data from `format.qkb.gov.al`

It produces several layers of output:

- raw fetched files stored on disk
- raw fetch metadata in `raw_fetches`
- latest logical source snapshots in `structured_records`
- normalized source-specific tables for APP and QKB search
- company-level feature tables for APP, QKB, and exact APP-to-QKB joins
- read-only profiling and audit JSON reports emitted by CLI commands

The supported production path is:

- `app_exports`
- `qkb_search`
- Alembic-managed schema changes
- normalization, feature materialization, profiling, audit, smoke checks, and scheduler support around those two collectors

The experimental path is:

- `qkb_notices_experimental`

That experimental notices path is intentionally separated from supported workflows. It stores raw pages and exploratory structured records, but it does not feed any normalization, feature, or profiling table.

Current overall state:

- The project is a serious prototype, not a finished warehouse.
- The supported collectors are meaningfully operational.
- QKB search is the primary QKB ingestion path.
- The repo now includes resumable date-range QKB search runs, raw-fetch corruption quarantine, smoke checks, and migration-backed schema management.
- The biggest remaining risks are upstream source-contract drift, the QKB 50-result cap for one-day searches, some dead or stale configuration/documentation, and the fact that experimental notices collection is still exploratory rather than authoritative.

## 2. High-Level Purpose

The project exists to build a traceable research dataset for Albanian procurement and business-registry analysis without pretending the source systems are cleaner or more joinable than they really are.

The business and research problem it solves is this:

- APP exports describe procurement events.
- QKB search results describe businesses and registry state.
- Those datasets are useful together, but only where they can be joined safely.

The pipeline therefore does four things deliberately:

1. It keeps raw source artifacts on disk so the collected evidence can be audited later.
2. It stores structured source snapshots in the database so normalization can be rerun without refetching live pages.
3. It materializes normalized source tables that preserve provenance back to raw and structured layers.
4. It only materializes a joined feature layer for exact `winner_nipt == business_nipt` matches.

That design avoids the main analytical failure mode for this kind of prototype: overconfident fuzzy joining and silent source drift.

## 3. External Sources

### APP procurement exports

- Base index page: `https://www.app.gov.al/export-public-calls/`
- Download pattern used by the collector: `https://www.app.gov.al/GetData/ExportDocument?year=YYYY`
- What it provides:
  - an index page listing available export years
  - yearly CSV exports with procurement rows
- Status:
  - supported
  - this is the most stable collector path in the repo

Important implementation note:

- The collector parses the index page to discover available years, but it still builds download URLs from the configured template rather than following discovered links directly.

### QKB subject search

- Search page: `https://format.qkb.gov.al/kerko-per-subjekt/`
- What it provides:
  - an HTML search form
  - an HTML response page that contains an inline JavaScript `response` payload
- Status:
  - supported
  - this is the primary QKB ingestion path

Important implementation notes:

- The collector is HTTP-only.
- It performs a GET first to establish session cookies, then POSTs the form payload.
- For non-NIPT date-range searches, it does not submit one multi-day query. It executes one inclusive one-day query per day.

### QKB notices index and category pages

- Index page: `https://qkb.gov.al/shpallje/`
- Configured category pages:
  - `https://format.qkb.gov.al/njoftime-gjyqesore/`
  - `https://format.qkb.gov.al/njoftime-per-kreditoret/`
  - `https://format.qkb.gov.al/njoftime-nga-zyra-permbarimore/`
  - `https://format.qkb.gov.al/njoftime-nga-organet-doganore/`
  - `https://format.qkb.gov.al/njoftime-per-regjistrin-e-pronareve-perfitues/`
  - `https://format.qkb.gov.al/njoftime-te-tjera/`
- What they provide in current implementation:
  - raw HTML snapshots
  - heuristic extraction of likely document links from category pages
- Status:
  - experimental only
  - not part of the supported production workflow

Important implementation notes:

- The notices path is split across two domains in configuration: `qkb.gov.al` for the index and `format.qkb.gov.al` for category pages.
- The collector does not feed any downstream normalized or feature table.
- The Playwright path only helps render and click; it does not turn the collector into a supported ingestion pipeline.

## 4. Architecture Overview

### Root-level files

- `README.md`
  - human-facing project overview and command examples
- `FULL_AUDIT_REPORT.md`
  - a prior audit/status report
- `changes_made.md`
  - recent change summary
- `run_examples.txt`
  - example commands, but some of them are stale and do not match current CLI behavior
- `pyproject.toml`
  - package metadata and runtime dependencies
- `requirements.txt`
  - installs the package in editable mode via `-e .`
- `.env.example`
  - environment-variable template
- `alembic.ini`
  - Alembic configuration

### Application package

- `src/albiz_collector/config.py`
  - loads `.env`
  - resolves project-relative paths
  - defines runtime settings
- `src/albiz_collector/db.py`
  - defines SQLAlchemy `Base`, engine, session factory, and `init_db()`
- `src/albiz_collector/models.py`
  - defines the application schema
- `src/albiz_collector/cli.py`
  - defines the Typer CLI entrypoints
- `src/albiz_collector/scheduler.py`
  - defines APScheduler jobs for APP and QKB search

### Source collection

- `src/albiz_collector/sources/base.py`
  - shared raw-file persistence
  - structured-record upsert behavior
- `src/albiz_collector/sources/app_exports.py`
  - APP procurement export collector
- `src/albiz_collector/sources/qkb_search.py`
  - supported QKB search collector
- `src/albiz_collector/sources/qkb_notices_experimental.py`
  - experimental notices collector

### Derived layers

- `src/albiz_collector/normalization/`
  - source-specific row parsing into normalized tables
- `src/albiz_collector/features/`
  - company-level aggregations and exact-match joined features
- `src/albiz_collector/profiling/`
  - read-only profiling of normalized and feature tables
- `src/albiz_collector/semantics/`
  - research join policy and field-semantics definitions

### Operational support

- `src/albiz_collector/audit/`
  - raw-fetch integrity scan and QKB run-state inspection
- `src/albiz_collector/smoke/`
  - live source-contract smoke checks for supported collectors only
- `src/albiz_collector/utils/`
  - HTTP client, hashing, storage helpers, time helpers, raw-fetch trust filters, logging

### Schema management and tests

- `alembic/`
  - migration environment and revision history
- `tests/`
  - parser, DB, normalization, features, profiling, semantics, scheduler, smoke, source, utility, and integration coverage

### How the parts connect

At a high level:

1. CLI commands open a DB session and call collectors or materializers.
2. Collectors fetch live content with `HttpClient`.
3. Raw bytes are written to disk and logged in `raw_fetches`.
4. A logical latest snapshot is upserted into `structured_records`.
5. Normalizers read structured snapshots and materialize source rows.
6. Feature builders aggregate normalized rows.
7. Profilers measure normalized and feature tables.
8. Audits and smoke checks validate storage integrity and live source contracts.
9. Scheduler automates collection only, not the derived layers.

## 5. End-to-End Data Flow

### Step 1: CLI input and runtime setup

Every CLI command enters through `src/albiz_collector/cli.py`.

Before a command runs:

- logging is configured
- `ensure_runtime_directories()` creates the raw-storage root if needed
- a DB session is opened with `SessionLocal()`

Commands return JSON to stdout by serializing dictionaries with `json.dumps(..., default=str)`.

### Step 2: Live fetch

All supported live HTTP work uses `HttpClient` from `src/albiz_collector/utils/http.py`.

Important runtime behavior:

- `httpx.Client(..., trust_env=True)` means shell proxy variables affect all live requests
- retryable transport errors and retryable HTTP responses are retried up to 3 attempts
- retryable HTTP statuses are `408`, `425`, `429`, and `5xx`

### Step 3: Raw artifact persistence

Collectors call `CollectorBase.save_raw_fetch()`.

That method:

- computes a SHA-256 hash of the raw bytes
- chooses an extension from content type or URL
- writes the bytes under a date-based path:
  - `<RAW_STORAGE_DIR>/<source_name>/<YYYY>/<MM>/<DD>/<fetch_kind>/<filename-with-hash>`
- inserts a `raw_fetches` row
- flushes so the row has an ID immediately

The filename logic is deliberately hash-suffixed even when the collector supplies a human-readable filename, which prevents later fetches from silently overwriting older files.

### Step 4: Structured snapshot persistence

Collectors then call `CollectorBase.upsert_structured_record()`.

This layer stores the latest logical snapshot per:

- `source_name`
- `record_type`
- `external_key`

That means:

- `structured_records` is not append-only
- the same logical snapshot key is updated in place over time
- historical raw fetches are preserved separately in `raw_fetches`

The supported collectors currently write these `record_type` values:

- `procurement_export_year`
- `qkb_search_snapshot`

The experimental notices collector additionally writes:

- `category_snapshot`
- `notice_document`

### Step 5: Source-specific parsing and normalization

Normalization is not done during collection. It is a separate CLI step.

#### APP path

`normalize app-exports`:

- loads `structured_records` where `source_name='app_exports'` and `record_type='procurement_export_year'`
- extracts `raw_fetch_id` from the structured payload
- loads the referenced `raw_fetches` row
- verifies the raw fetch is not quarantined
- rereads the saved CSV bytes from disk
- parses every CSV row into `normalized_app_export_rows`
- deletes prior normalized rows for that snapshot
- inserts the new rows

#### QKB search path

`normalize qkb-search`:

- loads `structured_records` where `source_name='qkb_search'` and `record_type='qkb_search_snapshot'`
- extracts `raw_fetch_id` from the structured payload
- verifies the raw fetch exists and is not quarantined
- does not reread the HTML for row parsing
- instead, normalizes from `structured_record.payload["response"]`
- deletes prior normalized rows for that snapshot
- inserts the new rows

This difference matters:

- APP normalization depends on the raw file contents themselves
- QKB search normalization depends on the previously parsed structured payload, with the raw fetch retained for provenance and trust gating

### Step 6: Feature materialization

Feature commands aggregate normalized rows into denormalized company-level tables.

#### APP features

- grouped by exact `winner_nipt`
- rows without `winner_nipt` are skipped

#### QKB features

- grouped by exact `business_nipt`
- rows without `business_nipt` are skipped

#### Joined features

- built only where exact NIPT equality exists
- no name-only joins are materialized

Feature materialization is full-table rebuild, not incremental update:

- the target feature table is fully deleted
- new rows are inserted from the current normalized layer

### Step 7: Profiling

Profiling commands are read-only.

They measure:

- row counts
- missingness of important fields
- exact APP-to-QKB join coverage
- feature sparsity using the confidence registry
- an analytical-readiness summary

`profile normalized` filters out rows tied to corrupted raw fetches.

`profile features` reads feature tables as they currently exist. If quarantine happened after the last feature rebuild, the feature tables must be rebuilt first.

### Step 8: Audit and quarantine

`audit raw-fetches`:

- resolves each `storage_path`
- rereads file bytes
- recomputes SHA-256
- compares to `raw_fetches.content_hash`
- reports missing files and mismatches
- can optionally set:
  - `is_corrupted = true`
  - `corruption_reason = ...`

The command does not:

- rewrite files
- recompute stored hashes
- delete rows

### Step 9: Resume, restart, and run tracking for QKB date ranges

For QKB date-range searches without `--nipt`:

- the collector creates or resumes a `qkb_search_runs` row
- the run stores requested window, current progress, status, timestamps, and last error
- progress advances only after a day completes successfully
- if the process fails on a day, the run is marked `failed` and `current_date` stays on that unfinished day
- rerunning the same unfinished range resumes from that saved day
- `--restart` interrupts unfinished matching runs and creates a new run row from the original start date

Completed runs are not resumed again. Repeating the same completed date range creates a new run row.

### Step 10: Scheduler and automation

The scheduler:

- uses `Europe/Tirane`
- schedules APP exports daily at `scheduler_app_exports_hour:00`
- optionally schedules QKB search daily at `scheduler_qkb_search_hour:15`
- computes QKB windows as:
  - `today - lookback_days` through `today`, inclusive

The scheduler only performs collection.

It does not automatically run:

- normalization
- feature materialization
- profiling
- raw-fetch audit

## 6. Command Surface Overview

### `python -m albiz_collector.cli init-db`

- lightweight schema bootstrap for current models
- creates missing tables only
- does not apply migrations
- not the preferred managed-schema path

### `python -m albiz_collector.cli run ...`

- supported one-shot collectors
- current supported commands:
  - `app-exports`
  - `qkb-search`

### `python -m albiz_collector.cli experimental ...`

- explicitly separated experimental collectors
- current command:
  - `qkb-notices`

### `python -m albiz_collector.cli normalize ...`

- builds normalized source datasets from stored snapshots

### `python -m albiz_collector.cli features ...`

- builds denormalized analytical feature tables

### `python -m albiz_collector.cli profile ...`

- read-only profiling and readiness reports

### `python -m albiz_collector.cli audit ...`

- raw storage integrity checks
- QKB resumable run-state inspection

### `python -m albiz_collector.cli smoke ...`

- live low-volume contract checks for supported sources only

### `python -m albiz_collector.cli scheduler`

- blocking scheduler process for recurring collection jobs

## 7. Collector Details

### 7.1 APP exports collector

Module:

- `src/albiz_collector/sources/app_exports.py`

What it does:

- fetches the APP export index page
- saves the raw HTML
- parses available years from the page
- downloads requested yearly CSV exports
- saves the raw CSV files
- upserts one `structured_records` snapshot per year

How it fetches:

- one GET to the index page
- one GET per requested year using the configured URL template

What it stores:

- `raw_fetches` rows with `fetch_kind='index_page'` and `fetch_kind='year_export'`
- one `structured_records` row per year with `record_type='procurement_export_year'`

What it outputs later:

- `normalized_app_export_rows`
- `app_company_features`
- potential contribution to `joined_company_features`

Supported or experimental:

- supported

Important caveats and limitations:

- The default year list is static and comes from `APP_EXPORT_YEARS`; it does not auto-expand to new future years unless configuration or CLI input changes.
- The collector parses discovered years from the index page, but it still constructs download URLs from `app_export_download_url_template`.
- `APP_DOWNLOAD_ENABLED` exists in settings but is not used in current collector code.

### 7.2 QKB search collector

Module:

- `src/albiz_collector/sources/qkb_search.py`

What it does:

- performs supported QKB business-registry collection
- saves the raw returned HTML page
- parses the inline JavaScript `response` payload
- upserts one structured snapshot per logical query window
- tracks resumable date-range progress in `qkb_search_runs`

How it fetches:

- GET the search page first to establish session cookies
- POST form-urlencoded data back to the same endpoint

How query modes work:

- exact `--nipt` search:
  - always one request
  - may optionally include dates
  - does not create a `qkb_search_runs` row
- date-range search without `--nipt`:
  - inclusive one-day chunking
  - one request per day
  - creates or resumes a `qkb_search_runs` row

What it stores:

- `raw_fetches` rows with `fetch_kind='search_results_page'`
- `structured_records` rows with `record_type='qkb_search_snapshot'`
- `qkb_search_runs` rows for date-range progress tracking

What it outputs later:

- `normalized_qkb_search_rows`
- `qkb_company_features`
- possible input to `joined_company_features`

Supported or experimental:

- supported

Important caveats and limitations:

- The parser depends on the page continuing to expose a JavaScript variable called `response`.
- One-day searches that return exactly `50` rows are only flagged as potentially truncated; the collector does not automatically split them further.
- There is no database-level uniqueness or locking on `qkb_search_runs`, so truly concurrent identical date-range invocations can still race operationally.

### 7.3 Experimental QKB notices collector

Module:

- `src/albiz_collector/sources/qkb_notices_experimental.py`

What it does:

- fetches the QKB notices index page
- fetches or renders configured category pages
- extracts likely document links from anchors
- stores either category snapshots or individual notice-document records

How it fetches:

- index page via HTTP GET
- category pages via HTTP GET unless `--playwright` is used
- with `--playwright`, the collector launches Chromium, visits each configured category page, tries to click the configured search button text, waits, then saves rendered HTML
- if Playwright import fails, it falls back to HTTP mode

What it stores:

- `raw_fetches` rows with `fetch_kind='index_page'` and `fetch_kind='category_page'`
- `structured_records` rows with:
  - `record_type='category_snapshot'` when no document links are parsed
  - `record_type='notice_document'` when document-like links are found

What it outputs:

- exploratory structured records only
- no normalizer
- no feature table
- no profiling layer

Supported or experimental:

- experimental only

Important caveats and limitations:

- This is not a full notices-ingestion pipeline.
- The document parser is heuristic and anchor-based.
- `QKB_NOTICES_DATE_FROM_SELECTOR` and `QKB_NOTICES_DATE_TO_SELECTOR` are defined in settings but unused in current code.
- It is intentionally excluded from the supported scheduler path and supported `run` CLI group.

## 8. Database Schema Overview

The schema is layered rather than fully normalized in a warehouse sense.

### Operational schema categories

#### Raw layer

- `raw_fetches`

Purpose:

- durable metadata for on-disk artifacts
- provenance and integrity anchor for downstream trust

#### Structured layer

- `structured_records`

Purpose:

- latest logical snapshots keyed by `(source_name, record_type, external_key)`

Important design note:

- there is no formal foreign key from `structured_records` to `raw_fetches`
- provenance back to raw fetches is embedded inside `payload["raw_fetch_id"]`

#### Operational run-state layer

- `qkb_search_runs`
- `alembic_version`

Purpose:

- resumable QKB search progress
- migration-head tracking

#### Normalized layer

- `normalized_app_export_rows`
- `normalized_qkb_search_rows`

Purpose:

- one row per source result or CSV row
- stable analytical basis with explicit provenance

#### Feature layer

- `app_company_features`
- `qkb_company_features`
- `joined_company_features`

Purpose:

- denormalized, rebuildable, company-level analytical convenience tables

#### Audit and quarantine state

There is no separate audit table.

Instead:

- `raw_fetches.is_corrupted`
- `raw_fetches.corruption_reason`

carry quarantine state inside the raw layer itself.

## 9. Table-by-Table Explanation

### `alembic_version`

- Category: operational
- Purpose: records the schema revision currently stamped into the target database
- How rows are created:
  - by Alembic during `upgrade`, `stamp`, or `downgrade`
- Lifecycle:
  - effectively one mutable row per database
- Constraints:
  - managed by Alembic, not declared in the application models
- Downstream role:
  - migration bookkeeping only

### `raw_fetches`

- Category: raw plus audit state
- Purpose:
  - records each saved raw artifact and the metadata needed to audit it later
- How rows are created:
  - every collector calls `save_raw_fetch()`
- Lifecycle:
  - mostly append-only
  - later mutable only for quarantine fields (`is_corrupted`, `corruption_reason`)
- Important constraints:
  - primary key only
  - no uniqueness constraint on URL, hash, or path
- Downstream role:
  - APP normalization rereads the file from `storage_path`
  - both normalizers require the referenced raw fetch to exist and not be quarantined
  - features and normalized profiling exclude rows tied to corrupted raw fetches
  - audit commands inspect and optionally quarantine this table

### `structured_records`

- Category: structured latest-snapshot layer
- Purpose:
  - stores one latest structured snapshot per logical external key
- How rows are created:
  - `upsert_structured_record()` inserts or updates by logical key
- Lifecycle:
  - upserted, not append-only
  - older logical state is overwritten in place at this layer
- Important constraints:
  - unique on `(source_name, record_type, external_key)`
- Downstream role:
  - normalization commands use this table as their starting point
  - `payload` carries source-specific structured snapshot content and raw-fetch provenance

### `qkb_search_runs`

- Category: operational
- Purpose:
  - tracks resumable date-range progress for QKB searches without `--nipt`
- How rows are created:
  - new row for a new date range
  - new row again for a restarted or rerun completed date range
- Lifecycle:
  - mutable while unfinished
  - statuses change across `running`, `failed`, `interrupted`, and `completed`
- Important constraints:
  - primary key only
  - no uniqueness on range, so multiple historical rows can exist for the same date window
- Downstream role:
  - collector resume/restart behavior
  - operator inspection through `audit qkb-search-runs`

### `normalized_app_export_rows`

- Category: normalized
- Purpose:
  - materialized procurement rows from APP yearly CSV snapshots
- How rows are created:
  - by `materialize_app_exports()`
- Lifecycle:
  - replaced per structured snapshot on rerun
  - not append-only at snapshot level
- Important constraints:
  - unique on `(structured_record_id, row_ordinal)`
  - foreign keys to `structured_records` and `raw_fetches`
- Downstream role:
  - source table for APP feature materialization
  - source table for normalized profiling
  - APP side of exact NIPT join analysis

### `normalized_qkb_search_rows`

- Category: normalized
- Purpose:
  - materialized business-registry result rows from QKB search snapshots
- How rows are created:
  - by `materialize_qkb_search()`
- Lifecycle:
  - replaced per structured snapshot on rerun
- Important constraints:
  - unique on `(structured_record_id, result_ordinal)`
  - foreign keys to `structured_records` and `raw_fetches`
- Downstream role:
  - source table for QKB feature materialization
  - source table for normalized profiling
  - QKB side of exact NIPT join analysis

### `app_company_features`

- Category: feature
- Purpose:
  - one aggregated row per exact APP winner NIPT
- How rows are created:
  - by `materialize_app_features()`
- Lifecycle:
  - full-table rebuild on each feature run
- Important constraints:
  - unique on `company_nipt`
- Downstream role:
  - procurement-side company analysis
  - input source for exact joined features conceptually, although joined materialization rebuilds from normalized rows directly

### `qkb_company_features`

- Category: feature
- Purpose:
  - one aggregated row per exact QKB business NIPT
- How rows are created:
  - by `materialize_qkb_features()`
- Lifecycle:
  - full-table rebuild on each feature run
- Important constraints:
  - unique on `company_nipt`
- Downstream role:
  - registry-side company analysis
  - conceptual source for joined features, although joined materialization rebuilds from normalized rows directly

### `joined_company_features`

- Category: feature
- Purpose:
  - one denormalized row per company that can be joined safely by exact NIPT
- How rows are created:
  - by `materialize_joined_features()`
- Lifecycle:
  - full-table rebuild on each feature run
- Important constraints:
  - unique on `company_nipt`
- Downstream role:
  - combined procurement plus registry analysis for defensible exact matches only

## 10. Column-by-Column Explanation

### `alembic_version`

- `version_num` (Alembic-managed string type, required): current schema revision identifier. Source: Alembic itself. Why it matters: tells `upgrade`, `current`, and `stamp` what revision the database claims to be on. Special note: the exact SQL type is backend-generated by Alembic and is not declared in application code.

### `raw_fetches`

- `id` (`INTEGER`, required, primary key): surrogate key for a persisted raw artifact. Source: database identity. Why it matters: downstream provenance joins and audit references use this ID.
- `source_name` (`VARCHAR(100)`, required): logical collector name such as `app_exports`, `qkb_search`, or `qkb_notices`. Source: `CollectorBase.source_name`. Why it matters: identifies which collector produced the row and supports filtering and storage grouping.
- `source_url` (`TEXT`, required): URL that produced the saved bytes. Source: final response URL or configured category URL. Why it matters: preserves provenance and helps debug upstream changes.
- `fetch_kind` (`VARCHAR(50)`, required): subtype of fetch such as `index_page`, `year_export`, `search_results_page`, or `category_page`. Source: collector call to `save_raw_fetch()`. Why it matters: distinguishes different artifacts from the same source and becomes part of the storage path.
- `status_code` (`INTEGER`, nullable): HTTP status code, or synthetic `200` for rendered Playwright pages. Source: live response metadata or experimental collector fallback logic. Why it matters: operational diagnostics.
- `content_type` (`VARCHAR(255)`, nullable): HTTP content type, or `text/html` for rendered Playwright pages. Source: response headers or experimental collector logic. Why it matters: file-extension guessing and debugging.
- `content_hash` (`VARCHAR(64)`, required): SHA-256 of the exact persisted bytes. Source: `sha256_bytes(content)` at save time. Why it matters: integrity audit compares stored and actual bytes against this value.
- `storage_path` (`TEXT`, required): on-disk file path of the saved artifact. Source: `build_storage_path()` plus hashed filename logic. Why it matters: APP normalization rereads files from here and audits resolve this path.
- `is_corrupted` (`BOOLEAN`, required): quarantine flag. Source: defaults `False`; later set by `audit raw-fetches --mark-corrupted` or manual DB intervention. Why it matters: corrupted rows are excluded from trusted downstream use.
- `corruption_reason` (`TEXT`, nullable): human-readable reason such as `content_hash mismatch` or `missing file`. Source: raw-fetch audit. Why it matters: tells operators why a row was quarantined.
- `extra_metadata` (`JSON`, nullable): source-specific fetch context. Source: collector-supplied metadata. Why it matters: preserves operational details such as APP year, QKB form payload, mode, or notices category without changing schema.
- `fetched_at` (`DATETIME`, required): UTC-naive fetch timestamp. Source: `utc_now_naive()` default. Why it matters: supports audit chronology and time-based inspection.

### `structured_records`

- `id` (`INTEGER`, required, primary key): surrogate key for a logical structured snapshot. Source: database identity. Why it matters: normalized rows reference this ID directly.
- `source_name` (`VARCHAR(100)`, required): collector name. Source: `CollectorBase.source_name`. Why it matters: participates in the logical uniqueness contract and identifies source family.
- `record_type` (`VARCHAR(100)`, required): structured snapshot subtype such as `procurement_export_year`, `qkb_search_snapshot`, `category_snapshot`, or `notice_document`. Source: collector call to `upsert_structured_record()`. Why it matters: determines how downstream code interprets `payload`.
- `external_key` (`VARCHAR(255)`, required): logical source key for the snapshot. Source: collector-defined key such as export year or `nipt|date_from|date_to`. Why it matters: unique upsert key and source-side identity at the snapshot layer.
- `title` (`TEXT`, nullable): human-readable snapshot title. Source: collector-generated description. Why it matters: operator readability only; not used for joins.
- `source_url` (`TEXT`, nullable): source URL associated with the logical snapshot. Source: collector response URL or notice-link URL. Why it matters: provenance and debugging.
- `published_at` (`DATETIME`, nullable): source or collection timestamp attached to the snapshot. Source: for supported APP and QKB collectors this is set to current collection time; for experimental notice documents it may be parsed from link text; for some records it is absent. Why it matters: supports chronology and visibility into snapshot recency.
- `company_name` (`TEXT`, nullable): optional company label field. Source: generic upsert helper argument. Why it matters: in current supported collectors it is not populated, so it is presently spare schema capacity rather than active logic.
- `external_id` (`VARCHAR(255)`, nullable): optional external identifier field separate from `external_key`. Source: generic upsert helper argument. Why it matters: currently unused by supported collectors.
- `content_hash` (`VARCHAR(64)`, required): logical snapshot hash. Source: usually the raw artifact hash for APP and QKB search snapshots; for experimental notice documents it is derived from `href + title`. Why it matters: quick change detection at snapshot level, though semantics vary slightly by record type.
- `payload` (`JSON`, nullable): source-specific structured snapshot body. Source: collector-built dictionary. Why it matters: this is the main source for normalization and provenance. For APP it contains year, raw fetch ID, and CSV preview; for QKB it contains search inputs, raw fetch ID, and parsed response rows.
- `first_seen_at` (`DATETIME`, required): first time this logical key was inserted. Source: `utc_now_naive()` at first upsert. Why it matters: stable lineage start for that logical key.
- `last_seen_at` (`DATETIME`, required): most recent time this logical key was inserted or refreshed. Source: `utc_now_naive()` on every upsert. Why it matters: signals the snapshot was re-observed even if the logical key stayed the same.

### `qkb_search_runs`

- `id` (`INTEGER`, required, primary key): run-state row ID. Source: database identity. Why it matters: returned in collector summaries and used for operator inspection.
- `collector_name` (`VARCHAR(100)`, required): currently always `qkb_search`. Source: collector code. Why it matters: future-proofs the table for other resumable collectors and supports filtering.
- `mode` (`VARCHAR(50)`, required): currently `daily_range`. Source: collector constant. Why it matters: identifies how the run should be interpreted.
- `date_from` (`DATE`, required): requested inclusive start date for the logical run. Source: CLI input after ISO-date parsing. Why it matters: part of the range identity.
- `date_to` (`DATE`, required): requested inclusive end date for the logical run. Source: CLI input after ISO-date parsing. Why it matters: part of the range identity.
- `current_date` (`DATE`, nullable): next unfinished one-day search to execute. Source: collector progress updates. Why it matters: resume starts from this date after failure or interruption. Special note: when querying SQLite manually with raw SQL, quote `"current_date"` or SQLite may interpret `current_date` as a built-in function instead of the column name.
- `status` (`VARCHAR(50)`, required): run status such as `running`, `completed`, `failed`, or `interrupted`. Source: collector lifecycle updates. Why it matters: operator-facing state machine and resume gating.
- `started_at` (`DATETIME`, required): when the run row was created. Source: `utc_now_naive()` when a new run starts. Why it matters: run chronology.
- `updated_at` (`DATETIME`, required): last status or progress update time. Source: collector progress/status updates. Why it matters: tells operators whether a run is advancing.
- `completed_at` (`DATETIME`, nullable): completion timestamp. Source: set only when the run finishes the full requested range. Why it matters: distinguishes completed from merely updated.
- `last_error` (`TEXT`, nullable): last saved failure or interruption reason. Source: exception string or interruption message. Why it matters: operator debugging and incident visibility.

### `normalized_app_export_rows`

- `id` (`INTEGER`, required, primary key): normalized APP row ID. Source: database identity. Why it matters: row-level identity for the normalized layer.
- `structured_record_id` (`INTEGER`, required, foreign key to `structured_records.id`): source snapshot pointer. Source: the structured record being materialized. Why it matters: groups rows back to one APP export snapshot.
- `raw_fetch_id` (`INTEGER`, nullable, foreign key to `raw_fetches.id`): raw CSV provenance pointer. Source: referenced raw fetch for the snapshot. Why it matters: audit and quarantine filtering depend on it.
- `snapshot_external_key` (`VARCHAR(255)`, required): copy of the structured snapshot key, usually the export year. Source: `structured_record.external_key`. Why it matters: convenient provenance without joining.
- `source_name` (`VARCHAR(100)`, required): source family, currently `app_exports`. Source: structured record. Why it matters: filtering and provenance.
- `source_url` (`TEXT`, nullable): APP download URL used for that export. Source: `structured_record.source_url`, falling back to `raw_fetch.source_url`. Why it matters: provenance.
- `materialized_at` (`DATETIME`, required): normalization timestamp. Source: `utc_now_naive()` during materialization. Why it matters: tells you when the normalized row was last rebuilt.
- `export_year` (`INTEGER`, required): export year for the CSV snapshot. Source: `structured_record.payload["year"]` or fallback to integer `external_key`. Why it matters: analytical partitioning and provenance.
- `row_ordinal` (`INTEGER`, required): 1-based row position inside the CSV. Source: enumerated during parsing. Why it matters: part of the uniqueness contract per snapshot.
- `procurement_reference` (`VARCHAR(255)`, nullable): procurement reference number. Source: CSV column `Numri_i_references`. Why it matters: strongest procurement-row identifier currently exposed by APP exports.
- `contracting_authority` (`TEXT`, nullable): contracting authority name. Source: CSV column `Autoriteti_kontraktues`. Why it matters: key procurement context dimension.
- `procurement_subject` (`TEXT`, nullable): free-text procurement subject. Source: CSV column `Objekti_i_prokurimit`. Why it matters: analytical context but not a safe join key.
- `procedure_type` (`VARCHAR(255)`, nullable): procedure type label. Source: CSV column `Lloji_i_procedures`. Why it matters: procurement process category and feature input.
- `contract_type` (`VARCHAR(255)`, nullable): contract type label. Source: CSV column `Tipi_i_kontrates`. Why it matters: procurement context and feature input.
- `publication_date` (`DATE`, nullable): publication date. Source: CSV column `Data_e_publikimit` parsed by `parse_date_value()`. Why it matters: main APP chronology field.
- `opening_date` (`DATE`, nullable): opening date. Source: CSV column `Data_e_hapjes`. Why it matters: secondary procurement timeline field.
- `closing_date` (`DATE`, nullable): closing date. Source: CSV column `Data_e_mbylljes`. Why it matters: secondary procurement timeline field.
- `is_cancelled` (`BOOLEAN`, nullable): cancellation flag. Source: CSV column `Anulluar` parsed through yes/no coercion. Why it matters: important operational outcome and feature input.
- `is_suspended` (`BOOLEAN`, nullable): suspension flag. Source: CSV column `Pezulluar` parsed through yes/no coercion. Why it matters: important operational outcome and feature input.
- `budget_limit_amount` (`NUMERIC(18,2)`, nullable): budget-limit value. Source: CSV column `Fondi_limit` parsed as decimal. Why it matters: procurement-size measure and feature input.
- `winner_name` (`TEXT`, nullable): winner name. Source: CSV column `Fituesi`. Why it matters: useful context; weaker than NIPT.
- `winner_nipt` (`VARCHAR(64)`, nullable): winner company identifier. Source: CSV column `NIPT_i_fituesit`. Why it matters: safest APP-side join key and APP feature group key.
- `winner_value_amount` (`NUMERIC(18,2)`, nullable): award value. Source: CSV column `Vlera_e_fituesit` parsed as decimal. Why it matters: outcome-value measure and feature input.
- `cpv_codes` (`TEXT`, nullable): CPV classification text. Source: CSV column `Kodet_CPV`. Why it matters: sector/category context, though still semi-structured.
- `source_payload` (`JSON`, nullable): full original CSV row as parsed strings. Source: the parsed CSV row dict. Why it matters: traceability and later re-interpretation without reopening the CSV.

### `normalized_qkb_search_rows`

- `id` (`INTEGER`, required, primary key): normalized QKB row ID. Source: database identity. Why it matters: row-level identity for the normalized layer.
- `structured_record_id` (`INTEGER`, required, foreign key to `structured_records.id`): source snapshot pointer. Source: the structured QKB snapshot being materialized. Why it matters: groups results back to one search snapshot.
- `raw_fetch_id` (`INTEGER`, nullable, foreign key to `raw_fetches.id`): raw HTML provenance pointer. Source: `payload["raw_fetch_id"]`, then explicitly refreshed from the trusted raw fetch during materialization. Why it matters: quarantine and provenance.
- `snapshot_external_key` (`VARCHAR(255)`, required): copy of the search snapshot key such as `M21528028T|none|none` or `all|2026-04-17|2026-04-17`. Source: `structured_record.external_key`. Why it matters: convenient provenance without a join.
- `source_name` (`VARCHAR(100)`, required): source family, currently `qkb_search`. Source: structured record. Why it matters: filtering and provenance.
- `source_url` (`TEXT`, nullable): source URL for the search snapshot. Source: structured record, backfilled from raw fetch if absent. Why it matters: provenance and debugging.
- `materialized_at` (`DATETIME`, required): normalization timestamp. Source: `utc_now_naive()` during materialization. Why it matters: rebuild timing.
- `result_ordinal` (`INTEGER`, required): 1-based result position inside the parsed `response` list. Source: enumerated during normalization. Why it matters: part of the per-snapshot uniqueness contract.
- `search_nipt` (`VARCHAR(64)`, nullable): NIPT used as a search input, if any. Source: structured payload field `nipt`. Why it matters: provenance for how this row was collected, not business identity.
- `search_date_from` (`DATE`, nullable): requested lower search bound. Source: structured payload field `data_nga`. Why it matters: snapshot provenance and search-window semantics.
- `search_date_to` (`DATE`, nullable): requested upper search bound. Source: structured payload field `data_ne`. Why it matters: snapshot provenance and search-window semantics.
- `business_nipt` (`VARCHAR(64)`, nullable): QKB business identifier. Source: parsed item field `nipti`. Why it matters: strongest QKB-side identity field and safest join key.
- `business_name` (`TEXT`, nullable): business legal name. Source: parsed item field `emriISubjektit`. Why it matters: company label and feature input.
- `trade_name` (`TEXT`, nullable): trade name. Source: parsed item field `emriTregtar`. Why it matters: contextual label, weaker than formal business name.
- `legal_form` (`VARCHAR(255)`, nullable): legal-form label. Source: parsed item field `formaLigjore`. Why it matters: stable registry classification and feature input.
- `registration_date` (`DATE`, nullable): registry registration date. Source: parsed item field `dataERegjistrimit`. Why it matters: key temporal field and basis for age-at-procurement features.
- `city` (`VARCHAR(255)`, nullable): city. Source: parsed item field `qyteti`. Why it matters: contextual metadata, not a safe join key.
- `ownership_text` (`VARCHAR(255)`, nullable): ownership/nationality text. Source: parsed item field `shtetesia`. Why it matters: registry context and possible later explanatory use.
- `subject_status` (`VARCHAR(255)`, nullable): registry status. Source: parsed item field `statusiISubjektit`. Why it matters: strong registry-state field and feature input.
- `subject_type` (`VARCHAR(255)`, nullable): subject type text. Source: parsed item field `tipiISubjektit`. Why it matters: available context, but sparsely populated in samples.
- `activity_text` (`TEXT`, nullable): free-text activity description. Source: parsed item field `sektoriIVeprimtarise`. Why it matters: useful context, but not a stable coded dimension.
- `administrators_text` (`TEXT`, nullable): administrator/shareholder text. Source: parsed item field `adminOrtakAksionar`. Why it matters: manual context only; not used for automated joins.
- `has_red_flags` (`BOOLEAN`, nullable): registry red-flag boolean. Source: parsed item field `showRedFlag` coerced by `coerce_bool()`. Why it matters: source-side risk signal and feature input.
- `source_payload` (`JSON`, nullable): full parsed QKB result item. Source: raw structured `response` item dict. Why it matters: traceability and future reinterpretation without reparsing HTML.

### `app_company_features`

- `id` (`INTEGER`, required, primary key): feature row ID. Source: database identity. Why it matters: table row identity.
- `company_nipt` (`VARCHAR(64)`, required): exact APP winner NIPT used as aggregation key. Source: normalized `winner_nipt`, uppercased and stripped. Why it matters: the company-level feature grain.
- `materialized_at` (`DATETIME`, required): feature rebuild time. Source: `utc_now_naive()` during materialization. Why it matters: tells you when the feature layer was regenerated.
- `source_row_count` (`INTEGER`, required): count of normalized APP rows included in the group. Source: aggregation over normalized rows. Why it matters: provenance strength and denominator for interpretation.
- `source_snapshot_count` (`INTEGER`, required): count of distinct structured snapshots contributing rows. Source: distinct `structured_record_id` count. Why it matters: indicates breadth of supporting snapshots.
- `source_structured_record_ids` (`JSON`, nullable): list of contributing snapshot IDs. Source: sorted distinct normalized `structured_record_id` values. Why it matters: direct provenance trace.
- `latest_winner_name` (`TEXT`, nullable): latest non-empty winner name seen in the group. Source: most recent sorted normalized row with non-empty `winner_name`. Why it matters: convenience label for the feature row.
- `first_procurement_date` (`DATE`, nullable): earliest publication date in the group. Source: minimum normalized `publication_date`. Why it matters: start of observed procurement activity.
- `last_procurement_date` (`DATE`, nullable): latest publication date in the group. Source: maximum normalized `publication_date`. Why it matters: end of observed procurement activity.
- `total_budget_limit_amount` (`NUMERIC(18,2)`, nullable): sum of available budget-limit amounts. Source: aggregated normalized `budget_limit_amount`. Why it matters: procurement exposure measure.
- `total_winner_value_amount` (`NUMERIC(18,2)`, nullable): sum of available winner-value amounts. Source: aggregated normalized `winner_value_amount`. Why it matters: award-value measure.
- `cancelled_procurement_count` (`INTEGER`, required): count of rows with `is_cancelled is True`. Source: aggregation. Why it matters: cancellation signal.
- `suspended_procurement_count` (`INTEGER`, required): count of rows with `is_suspended is True`. Source: aggregation. Why it matters: suspension signal.
- `distinct_contracting_authority_count` (`INTEGER`, required): count of distinct non-empty authorities. Source: aggregation. Why it matters: breadth of authority relationships.
- `distinct_procedure_type_count` (`INTEGER`, required): count of distinct non-empty procedure types. Source: aggregation. Why it matters: procedural diversity.
- `distinct_contract_type_count` (`INTEGER`, required): count of distinct non-empty contract types. Source: aggregation. Why it matters: contract diversity.
- `has_small_value_procedures` (`BOOLEAN`, required): whether any grouped procedure type contains `small value`. Source: case-insensitive string match. Why it matters: simple procedural indicator.
- `has_open_local_procedures` (`BOOLEAN`, required): whether any grouped procedure type contains `open local`. Source: case-insensitive string match. Why it matters: simple procedural indicator.

### `qkb_company_features`

- `id` (`INTEGER`, required, primary key): feature row ID. Source: database identity. Why it matters: table row identity.
- `company_nipt` (`VARCHAR(64)`, required): exact business NIPT used as aggregation key. Source: normalized `business_nipt`, uppercased and stripped. Why it matters: company-level feature grain.
- `materialized_at` (`DATETIME`, required): feature rebuild time. Source: `utc_now_naive()` during materialization. Why it matters: rebuild timing.
- `source_row_count` (`INTEGER`, required): count of normalized QKB rows in the group. Source: aggregation. Why it matters: provenance and support size.
- `source_snapshot_count` (`INTEGER`, required): count of distinct snapshots in the group. Source: distinct `structured_record_id` count. Why it matters: breadth of source observation.
- `source_structured_record_ids` (`JSON`, nullable): list of contributing snapshot IDs. Source: sorted distinct normalized `structured_record_id` values. Why it matters: provenance trace.
- `business_name` (`TEXT`, nullable): latest non-empty business name. Source: latest ordered normalized row. Why it matters: convenience label.
- `trade_name` (`TEXT`, nullable): latest non-empty trade name. Source: latest ordered normalized row. Why it matters: secondary label.
- `legal_form` (`VARCHAR(255)`, nullable): latest non-empty legal form. Source: latest ordered normalized row. Why it matters: company classification.
- `subject_status` (`VARCHAR(255)`, nullable): latest non-empty status. Source: latest ordered normalized row. Why it matters: registry-state signal.
- `registration_date` (`DATE`, nullable): representative registration date from the latest ordered row. Source: the selected representative row, not a min/max across history. Why it matters: age-based feature input. Special note: if registry data changed historically, this field reflects the current representative row rather than a merged history.
- `registration_year` (`INTEGER`, nullable): year extracted from `registration_date`. Source: derived during feature materialization. Why it matters: coarse temporal grouping.
- `city` (`VARCHAR(255)`, nullable): latest non-empty city. Source: latest ordered normalized row. Why it matters: contextual location metadata.
- `has_red_flags` (`BOOLEAN`, nullable): representative red-flag value. Source: representative normalized row only. Why it matters: source-side risk signal. Special note: this is not an `any-ever-true` aggregation.
- `has_activity_text` (`BOOLEAN`, required): whether any grouped row has non-empty activity text. Source: aggregation across grouped normalized rows. Why it matters: indicates descriptive registry context is present.
- `has_ownership_text` (`BOOLEAN`, required): whether any grouped row has non-empty ownership text. Source: aggregation across grouped normalized rows. Why it matters: indicates ownership context is present.
- `search_window_start` (`DATE`, nullable): earliest search lower bound seen in the group. Source: minimum normalized `search_date_from`. Why it matters: provenance for the observed coverage window.
- `search_window_end` (`DATE`, nullable): latest search upper bound seen in the group. Source: maximum normalized `search_date_to`. Why it matters: provenance for the observed coverage window.

### `joined_company_features`

- `id` (`INTEGER`, required, primary key): feature row ID. Source: database identity. Why it matters: table row identity.
- `company_nipt` (`VARCHAR(64)`, required): exact NIPT present in both APP and QKB feature inputs. Source: exact aggregation key after join assessment. Why it matters: joined-company grain.
- `materialized_at` (`DATETIME`, required): feature rebuild time. Source: `utc_now_naive()` during materialization. Why it matters: rebuild timing.
- `app_source_row_count` (`INTEGER`, required): APP normalized-row count supporting this joined company. Source: copied from the in-memory APP aggregation. Why it matters: APP-side provenance.
- `app_source_snapshot_count` (`INTEGER`, required): distinct APP snapshot count supporting this company. Source: copied from the APP aggregation. Why it matters: APP-side provenance breadth.
- `app_structured_record_ids` (`JSON`, nullable): contributing APP snapshot IDs. Source: copied from the APP aggregation. Why it matters: direct APP provenance trace.
- `qkb_source_row_count` (`INTEGER`, required): QKB normalized-row count supporting this joined company. Source: copied from the in-memory QKB aggregation. Why it matters: QKB-side provenance.
- `qkb_source_snapshot_count` (`INTEGER`, required): distinct QKB snapshot count supporting this company. Source: copied from the QKB aggregation. Why it matters: QKB-side provenance breadth.
- `qkb_structured_record_ids` (`JSON`, nullable): contributing QKB snapshot IDs. Source: copied from the QKB aggregation. Why it matters: direct QKB provenance trace.
- `exact_join_match` (`BOOLEAN`, required): exact-identifier join indicator. Source: current code always sets `True` after `assess_app_qkb_join()` accepts the pair. Why it matters: makes the join policy explicit in the materialized table.
- `business_name` (`TEXT`, nullable): QKB business name. Source: copied from QKB features. Why it matters: readable company label.
- `legal_form` (`VARCHAR(255)`, nullable): QKB legal form. Source: copied from QKB features. Why it matters: registry enrichment.
- `subject_status` (`VARCHAR(255)`, nullable): QKB status. Source: copied from QKB features. Why it matters: registry enrichment.
- `city` (`VARCHAR(255)`, nullable): QKB city. Source: copied from QKB features. Why it matters: contextual registry enrichment only.
- `registration_date` (`DATE`, nullable): QKB registration date. Source: copied from QKB features. Why it matters: basis for age-at-procurement calculations.
- `first_procurement_date` (`DATE`, nullable): APP earliest publication date. Source: copied from APP features. Why it matters: APP chronology in joined context.
- `last_procurement_date` (`DATE`, nullable): APP latest publication date. Source: copied from APP features. Why it matters: APP chronology in joined context.
- `company_age_days_at_first_procurement` (`INTEGER`, nullable): days from registration to first procurement date. Source: derived during join materialization. Why it matters: temporal enrichment for exact joins.
- `company_age_days_at_last_procurement` (`INTEGER`, nullable): days from registration to last procurement date. Source: derived during join materialization. Why it matters: temporal enrichment for exact joins.
- `total_budget_limit_amount` (`NUMERIC(18,2)`, nullable): APP-side total budget amount. Source: copied from APP features. Why it matters: procurement exposure in joined context.
- `total_winner_value_amount` (`NUMERIC(18,2)`, nullable): APP-side total winner-value amount. Source: copied from APP features. Why it matters: procurement outcome value in joined context.
- `cancelled_procurement_count` (`INTEGER`, required): APP-side cancellation count. Source: copied from APP features. Why it matters: procurement risk context.
- `suspended_procurement_count` (`INTEGER`, required): APP-side suspension count. Source: copied from APP features. Why it matters: procurement risk context.
- `has_red_flags` (`BOOLEAN`, nullable): QKB-side red-flag signal. Source: copied from QKB features. Why it matters: registry-side risk context for exact joins.

## 11. Migrations and Schema Evolution

### Alembic configuration

Alembic is configured through:

- `alembic.ini`
- `alembic/env.py`

Important behavior in `alembic/env.py`:

- it loads the application's model metadata through `load_model_definitions()`
- it overrides `sqlalchemy.url` with `settings.database_url`
- it enables `compare_type=True`
- it leaves `compare_server_default=False`
- it enables SQLite batch mode when the target dialect is SQLite
- it suppresses empty autogenerate revisions through `process_revision_directives()`

### Revision history

#### `f7d09ee5b728` - baseline current schema

Creates the baseline application tables for a fresh database:

- `raw_fetches`
- `structured_records`
- `normalized_app_export_rows`
- `normalized_qkb_search_rows`
- `app_company_features`
- `qkb_company_features`
- `joined_company_features`

At this point:

- `raw_fetches` does not yet have corruption-quarantine fields
- `qkb_search_runs` does not yet exist

#### `aaef71721e11` - add raw fetch corruption quarantine

Adds to `raw_fetches`:

- `is_corrupted`
- `corruption_reason`
- index on `is_corrupted`

This revision formalizes quarantine state rather than keeping corruption handling purely external.

#### `9f2e4a8c1b6d` - add QKB search run tracking

Creates:

- `qkb_search_runs`

This revision makes QKB date-range progress durable and queryable.

### How schema changes should happen now

Supported current approach:

1. change SQLAlchemy models
2. generate a migration with Alembic autogenerate
3. review the migration manually
4. apply with `upgrade head`

For fresh databases:

- use Alembic `upgrade head`

For already-existing databases that already match the current schema exactly:

- use `stamp head`

`init-db` remains useful for lightweight local bootstrap, but it is not the managed migration path and does not create or update `alembic_version` until you explicitly stamp or migrate.

## 12. Tests and Verification

### What kinds of tests exist

- parser tests:
  - APP index parsing
  - APP preview parsing
  - QKB search response extraction
  - notices document parsing
- DB/bootstrap tests:
  - schema bootstrap expectations
  - collector persistence helper behavior
- normalization tests:
  - APP normalization
  - QKB normalization
  - rerun safety
  - corrupted raw-fetch skipping
- feature tests:
  - APP, QKB, and joined feature materialization
  - rerun safety
  - corruption-aware filtering
- profiling tests:
  - missingness, join coverage, readiness behavior
- semantics tests:
  - exact-join policy and join-assessment rules
- scheduler tests:
  - Europe/Tirane date semantics
- smoke evaluation tests:
  - source-contract parsing logic without live network
- source collector tests:
  - QKB search chunking, truncation reporting, resume, restart, and completion behavior
- utility tests:
  - HTTP retry classification
  - storage-path resolution
- integration tests:
  - opt-in MySQL migration/bootstrap/normalization path

### What they cover well

- supported QKB search collector behavior
- normalized-table rebuild safety
- feature-table rebuild safety
- exact-join policy enforcement
- raw-fetch audit and corruption handling
- scheduler timezone behavior
- smoke-check evaluation logic

### What they do not cover fully

- live end-to-end collection in CI
- full experimental notices ingestion behavior as a production flow
- deeper hosted MySQL CI as a required gate
- PostgreSQL runtime behavior
- concurrent identical QKB date-range invocations under load

### CI overview

`.github/workflows/ci.yml` defines:

- default `unit-tests` job on Python `3.11` and `3.12`
- optional manual `mysql-integration` job on `workflow_dispatch`

The default CI does not run:

- live smoke checks
- live collectors
- the MySQL integration job on every push or PR

### Verification performed during this documentation pass

The following were actually verified in this environment:

- full unit suite:
  - `python -m unittest discover -s tests -p "test_*.py" -v`
  - result: `61` tests passed
- CLI help surface for:
  - root CLI
  - `run`
  - `run qkb-search`
  - `normalize`
  - `features`
  - `profile`
  - `audit`
  - `audit raw-fetches`
  - `audit qkb-search-runs`
  - `smoke`
  - `experimental qkb-notices`
- Alembic on disposable SQLite databases:
  - `upgrade head`
  - `stamp head`
  - `heads`
- empty-database command behavior on disposable SQLite:
  - `normalize all`
  - `features all`
  - `profile all`
  - `audit raw-fetches`
  - `audit qkb-search-runs`
- live smoke checks after unsetting dead proxy variables:
  - APP source contract passed
  - QKB search source contract passed
- minimal live supported flow on a disposable SQLite DB and disposable raw-storage directory:
  - `run app-exports --years 2026`
  - `run qkb-search --nipt M21528028T`
  - `run qkb-search --data-nga 2026-04-17 --data-ne 2026-04-17`
  - `normalize all`
  - `features all`
  - `profile all`
  - `audit raw-fetches`
  - `audit qkb-search-runs`

The MySQL integration suite exists in the repo but was not rerun in this documentation pass.

## 13. Operational Behavior

### Raw-fetch integrity audit

`audit raw-fetches` works by:

- scanning every selected `raw_fetches` row
- resolving its file path with backward-compatible path lookup
- hashing on-disk bytes
- comparing them to `content_hash`

If `--mark-corrupted` is used:

- only metadata is updated
- no file bytes are changed
- no raw rows are deleted

### Quarantine behavior

Quarantine is controlled by:

- `raw_fetches.is_corrupted`
- `raw_fetches.corruption_reason`

Downstream behavior is intentionally asymmetric:

- normalization refuses to materialize from a quarantined raw fetch
- normalized profiling excludes normalized rows joined to a corrupted raw fetch
- feature materialization excludes normalized rows joined to a corrupted raw fetch

But:

- already-materialized normalized rows for a now-corrupted snapshot are not automatically deleted when the snapshot is skipped later
- already-materialized feature tables are not automatically rebuilt by the audit command

Operational consequence:

- after quarantining rows, rerun feature materialization and profiling if you want derived outputs to reflect the trusted subset
- rerunning normalization can refresh stats and future materialization, but it still will not automatically purge existing normalized rows for skipped corrupted snapshots

### Normalization expectations

- normalization is rerunnable
- per-snapshot normalized rows are deleted and reinserted when a snapshot materializes successfully
- normalization is source-specific:
  - APP rereads raw CSV bytes
  - QKB search reuses structured parsed payload plus raw-fetch trust checks

### Feature rebuild expectations

- every feature command rebuilds the entire target table
- `features joined` does not depend on previously materialized `app_company_features` or `qkb_company_features`; it recomputes the necessary source aggregations from normalized rows in memory

### QKB resume and restart behavior

- only non-NIPT date-range QKB searches use run tracking
- progress commits only after each successful day
- failures stop the run on the first failed day
- rerunning the same unfinished range resumes from `current_date`
- `--restart` interrupts unfinished matching runs and starts a new run row

### Scheduler behavior

- scheduler timezone is hard-coded to `Europe/Tirane`
- scheduler automates collection only
- it does not run normalization, features, profiling, or audit automatically

### Live source-contract smoke behavior

- smoke checks are read-only
- they do not touch the DB
- they honor proxy environment variables because `HttpClient` uses `trust_env=True`

## 14. Current Risks and Limitations

- `qkb_search` depends on the current inline JavaScript `response` contract in the returned HTML.
- One-day QKB date-range searches that return exactly `50` rows are only flagged as potentially truncated; the collector does not automatically split those days further.
- The APP collector uses a configured download URL template rather than following discovered download links from the page.
- The default APP year set is static in configuration, so a newly published future year will not be collected by default until configuration or CLI input changes.
- `structured_records` stores raw-fetch provenance inside JSON payload rather than a formal foreign key, so referential integrity between structured and raw layers is application-enforced, not database-enforced.
- `APP_DOWNLOAD_ENABLED` exists in settings and `.env.example` but is not used by current code.
- `APP_ENV` is loaded into settings but is not used for any runtime branching in current code.
- `QKB_NOTICES_DATE_FROM_SELECTOR` and `QKB_NOTICES_DATE_TO_SELECTOR` are defined but unused.
- The experimental notices collector is still exploratory and has no downstream normalized or feature layer.
- The scheduler does not automate the derived layers, so collection alone does not keep analytical tables current.
- The feature layer has no incremental update path; it always rebuilds full tables.
- The project's current operational default is MySQL, and tests also use SQLite, but the repo still carries a `psycopg[binary]` dependency and the README still mentions PostgreSQL as a suggested metadata store. That is not backed by current default configuration or integration coverage.
- `run_examples.txt` contains stale commands:
  - it still uses `run qkb-notices` instead of `experimental qkb-notices`
  - it still shows `run qkb-search --playwright`, but the supported QKB search collector no longer exposes a Playwright mode
  - it implies scheduler behavior for notices that current scheduler code does not implement
- The checked-in `collector.db` file in the repo root is not referenced by current default configuration, which can confuse new operators into thinking SQLite is still the active default.
- There is no retention policy yet for:
  - old raw files
  - historical `qkb_search_runs`
  - overwritten logical snapshots at the raw layer

## 15. Practical Summary

If a new engineer joined today, the first things they need to understand are:

1. The supported pipeline is `app_exports` plus `qkb_search`. `qkb_notices_experimental` is intentionally not in that lane.
2. The system is layered: raw files -> `raw_fetches` -> `structured_records` -> normalized tables -> feature tables -> profiling output.
3. Alembic is the schema source of truth for managed changes. `init-db` is only a bootstrap convenience.
4. Exact NIPT equality is the only automated APP-to-QKB join the project currently considers safe enough to materialize.
5. Quarantine is metadata-only. It changes what downstream code trusts, but it does not clean up old derived rows automatically.
6. Proxy environment variables matter for every live HTTP operation.
7. Some root-level docs are stale. For current behavior, trust the code, the CLI help, the Alembic revisions, and the test suite over older examples.
