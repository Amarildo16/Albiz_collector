# Albanian Business Collector

Prototype data-collection pipeline for an Albanian business-risk/performance thesis.

What it does today:
- Downloads APP procurement CSV exports by year.
- Collects QKB subject-search results via a session-initializing GET followed by a form POST to the official search endpoint.
- Captures QKB notice-category pages for exploratory document/link discovery.
- Materializes normalized APP and QKB search datasets from stored raw/structured snapshots.
- Stores raw fetched artifacts on disk.
- Stores normalized metadata in SQLAlchemy models.
- Can run on demand or on a schedule.

What it does **not** claim yet:
- A fully reverse-engineered QKB notices API.
- Bulletproof parsing of every JS-driven QKB result page.
- Production-grade anti-breakage monitoring out of the box.

This project is intentionally designed as a safe first version:
- official-first sources,
- raw-content retention for auditability,
- idempotent-ish upserts,
- modest scheduler cadence,
- explicit notes where the live site still needs selector tuning.

## Collector maturity

- `app_exports` is the strongest stable baseline in the repo.
- `qkb_search` is the primary QKB path and is the QKB collector to harden further.
- `qkb_notices_experimental` remains experimental and is best treated as exploratory snapshot/link discovery, not a stable ingestion pipeline.

## Sources included

### 1) APP procurement exports
Current source page:
- `https://www.app.gov.al/export-public-calls/`

Current download pattern observed on the source page:
- `https://www.app.gov.al/GetData/ExportDocument?year=YYYY`

### 2) QKB notices
Main category page:
- `https://qkb.gov.al/shpallje/`

Category pages currently configured:
- `https://format.qkb.gov.al/njoftime-gjyqesore/`
- `https://format.qkb.gov.al/njoftime-per-kreditoret/`
- `https://format.qkb.gov.al/njoftime-nga-zyra-permbarimore/`
- `https://format.qkb.gov.al/njoftime-nga-organet-doganore/`
- `https://format.qkb.gov.al/njoftime-per-regjistrin-e-pronareve-perfitues/`
- `https://format.qkb.gov.al/njoftime-te-tjera/`

### 3) QKB subject search
- `https://format.qkb.gov.al/kerko-per-subjekt/`

## Quick start

Use Python `3.11` or `3.12`; Python `3.12` is the locally verified path.

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1  # PowerShell
# source .venv/bin/activate   # bash/zsh
python -m pip install -r requirements.txt
python -m playwright install chromium  # Only needed for experimental qkb-notices browser-assisted runs
Copy-Item .env.example .env  # PowerShell
# cp .env.example .env       # bash/zsh
```

`requirements.txt` installs the package in editable mode and pulls runtime dependencies from `pyproject.toml`.

Edit the copied `.env` for your local database and storage settings. Never commit `.env`; it is intentionally ignored. The project loads `.env` from the repository root, so commands run from another working directory use the same configuration. Relative `RAW_STORAGE_DIR` values and relative SQLite file URLs are resolved from the repository root.

The default database URL is now MySQL via `PyMySQL`. Override `DATABASE_URL` in `.env` if you need a different MySQL user, password, host, or database name.

Live HTTP collector runs use `httpx` with environment-derived proxy settings enabled. If `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, or related variables point to a dead proxy, collector requests will fail until those variables are corrected or unset.

Run schema migrations:

```bash
alembic upgrade head
```

Alembic uses the same `DATABASE_URL` loaded by the project itself from `.env` / environment variables. The SQLAlchemy models remain the source of truth for future `--autogenerate` revisions.

Existing database adoption:
- if your database already matches the current schema, run `alembic stamp head` once
- `stamp head` records the baseline revision in Alembic's version table without recreating application tables
- do not run `alembic upgrade head` against an already-populated pre-migration database unless it is actually behind the recorded revision history

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

The Alembic env is configured to reject empty autogenerate revisions. If no schema changes are detected, no revision file is created.

Legacy bootstrap command:

```bash
python -m albiz_collector.cli init-db
```

`init-db` is still available as a lightweight local bootstrap command, but Alembic is now the supported path for managed schema changes.

Current schema contract:
- fresh databases should use `alembic upgrade head`
- existing databases that already match the current models should use `alembic stamp head`
- future schema changes should be applied through Alembic revisions, not manual DB recreation

Run the fast default unit suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run the DB-focused unit suite:

```bash
python -m unittest discover -s tests/db -p "test_*.py" -v
```

Run the normalization-focused unit suite:

```bash
python -m unittest discover -s tests/normalization -p "test_*.py" -v
```

Run the opt-in MySQL integration suite:

```bash
$env:RUN_MYSQL_INTEGRATION_TESTS="1"  # PowerShell
python -m unittest discover -s tests/integration -p "*_integration.py" -v
```

Optional MySQL admin URL override for integration tests:
- `MYSQL_INTEGRATION_ADMIN_URL=mysql+pymysql://root:password@127.0.0.1:3306/mysql`

Test layout:
- parser tests live in `tests/parsers/`
- DB tests live in `tests/db/`
- scheduler tests live in `tests/scheduler/`
- smoke-check evaluation tests live in `tests/smoke/`
- source-collector tests live in `tests/sources/`
- integration tests live in `tests/integration/` and are opt-in
- intentional fixture files live in `tests/fixtures/`
- runtime collector output under `data/raw/` is not part of the test suite

Run APP export collection:

```bash
python -m albiz_collector.cli run app-exports
```

Run QKB notices collection without browser automation (experimental snapshot mode):

```bash
python -m albiz_collector.cli experimental qkb-notices
```

Run QKB notices with Playwright (experimental browser-assisted snapshot mode):

```bash
python -m albiz_collector.cli experimental qkb-notices --playwright
```

Run QKB subject search (primary QKB path):

```bash
python -m albiz_collector.cli run qkb-search --nipt M21528028T
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --restart
```

QKB search is intentionally HTTP-only.

For date-range searches without `--nipt`, the collector does not submit the full range in one request. It executes one inclusive one-day search per day in the requested window:
- `2026-04-01` through `2026-04-03` becomes three searches:
- `2026-04-01 -> 2026-04-01`
- `2026-04-02 -> 2026-04-02`
- `2026-04-03 -> 2026-04-03`

Exact `--nipt` searches keep the single-request behavior even when both dates are provided.

QKB returns at most `50` rows per search. If any one-day search returns exactly `50` rows, the collector reports that day in `potentially_truncated_days` so it is not silently treated as complete.

QKB date-range runs are now resumable and their progress is stored in the database:
- the collector creates a persisted run row for each date-range invocation
- `current_date` tracks the next unfinished day
- if the same unfinished date range is run again, it resumes from that saved day instead of restarting from the beginning
- completed runs are not resumed again; rerunning the same completed range starts a new run
- `--restart` forces a fresh run from `date_from` and interrupts any unfinished saved run for the same range

Run one QKB subject document fetch (experimental):

```bash
python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt M21528028T --doc-type historical --no-save
python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt M21528028T --doc-type simple --no-save
python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt M21528028T --doc-type rpp --no-save
python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt M21528028T --doc-type historical --save
```

This command is intentionally limited to one NIPT and one allowlisted document type: `historical`, `simple`, or `rpp`. It posts the public form fields `nipt` and `docType`, does not accept credentials or cookie values, decodes the JSON base64 PDF response, verifies `%PDF`, and prints a JSON probe summary. `--no-save` performs no database or RawFetch writes; `--save` persists only a successful verified PDF as a `RawFetch`. There is no batch document collector and no PDF parsing in this experimental path.

Materialize normalized datasets:

```bash
python -m albiz_collector.cli normalize app-exports
python -m albiz_collector.cli normalize qkb-search
python -m albiz_collector.cli normalize all
```

Normalization reruns are safe: the commands replace normalized rows for the same source snapshot instead of accumulating duplicates.

Materialize baseline analytical features:

```bash
python -m albiz_collector.cli features app
python -m albiz_collector.cli features qkb
python -m albiz_collector.cli features joined
python -m albiz_collector.cli features all
```

Feature reruns are safe: the commands replace the current feature tables and rebuild them from normalized data.

Profile normalized and feature datasets:

```bash
python -m albiz_collector.cli profile normalized
python -m albiz_collector.cli profile features
python -m albiz_collector.cli profile all
```

The profiling commands are read-only and report row counts, missingness, exact-join coverage, feature sparsity, and a small analytical-readiness summary for the current local dataset.

Audit persisted raw fetch integrity:

```bash
python -m albiz_collector.cli audit raw-fetches
python -m albiz_collector.cli audit raw-fetches --source-name qkb_search --limit 25
python -m albiz_collector.cli audit raw-fetches --mark-corrupted
python -m albiz_collector.cli audit raw-fetches --corrupted-only
```

The audit command reports raw fetch rows whose persisted `content_hash` no longer matches on-disk content and rows whose files are missing.

When you add `--mark-corrupted`, the command does not rewrite files, hashes, or raw artifacts. It only marks affected `raw_fetches` rows with:
- `is_corrupted = true`
- `corruption_reason = ...`

Downstream normalization, feature materialization, and normalized-data profiling ignore quarantined raw fetches. After quarantining rows in an existing database, rebuild the derived layers that should reflect the trusted subset:

```bash
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

Rerun `normalize all` as well when you need refreshed normalization stats from the currently trusted snapshots.

Inspect persisted qkb-search resumable run state:

```bash
python -m albiz_collector.cli audit qkb-search-runs
python -m albiz_collector.cli audit qkb-search-runs --status failed
python -m albiz_collector.cli audit qkb-search-runs --limit 25
```

This audit view lists saved qkb-search date-range runs, including:
- requested date window
- next unfinished `current_date`
- run status
- timestamps
- last saved error

Run opt-in live source-contract smoke checks for the supported production collectors:

```bash
python -m albiz_collector.cli smoke app
python -m albiz_collector.cli smoke qkb-search
python -m albiz_collector.cli smoke all
```

These smoke checks are intentionally manual and low-volume. They only touch:
- the APP export index page
- the QKB search page

If stale proxy variables are set in your shell, unset them first or the smoke checks will fail for connectivity reasons rather than source-contract drift.

Start the scheduler:

```bash
python -m albiz_collector.cli scheduler
```

Scheduler intent:
- local recurring collection for the most useful baseline jobs
- `app_exports` is scheduled by default
- `qkb_search` is scheduled by default with a configurable rolling lookback window
- experimental collectors are not scheduled automatically

See [docs/deployment_and_migration_runbook.md](docs/deployment_and_migration_runbook.md) for the operational runbook covering fresh DB setup, existing DB adoption, migrations, smoke checks, integration tests, maintenance commands, and the supported production flow.

## Suggested deployment

For a thesis prototype:
- collector service in Python,
- PostgreSQL for metadata,
- raw files stored on disk or object storage,
- Laravel only as dashboard/API layer.

## Tables

### `raw_fetches`
Stores the raw fetch artifact reference and metadata.

### `structured_records`
Stores normalized records such as:
- APP yearly export metadata,
- exploratory notice documents and category snapshots,
- QKB search snapshots,
- page snapshots when the source is JS-driven and needs further tuning.

### `normalized_app_export_rows`
Materialized APP procurement rows with provenance back to structured snapshots and raw CSV fetches.

### `normalized_qkb_search_rows`
Materialized QKB subject-search results with provenance back to structured snapshots and raw search pages.

### `app_company_features`
Baseline company-level APP aggregates built only from normalized APP rows with exact winner NIPT.

### `qkb_company_features`
Baseline company-level QKB registry features built only from normalized QKB rows with exact business NIPT.

### `joined_company_features`
Baseline exact-match APP to QKB company features built only where APP `winner_nipt == business_nipt`.

## Research Dataset Design

Current research-ready interpretation:
- `normalized_app_export_rows` is the procurement-event dataset.
- `normalized_qkb_search_rows` is the business-registry dataset.
- the safest automated APP to QKB join is exact `winner_nipt -> business_nipt` only.
- rows without exact business identifiers should remain in separate source datasets rather than being force-joined.

See [docs/research_dataset_design.md](docs/research_dataset_design.md) for field classifications, join policy, and later feature candidates.

See [docs/feature_layer_design.md](docs/feature_layer_design.md) for the baseline feature tables, confidence boundaries, and feature materialization commands.

See [docs/data_profiling_readiness.md](docs/data_profiling_readiness.md) for profiling commands and the analytical-readiness summary structure.

## Notes on QKB pages

The supported QKB search collector is intentionally HTTP-only. It uses the official search page by first performing a GET request to establish session cookies and then POSTing the form-urlencoded search payload back to the same endpoint. The returned HTML is persisted raw and the JavaScript `response` variable is decoded into a structured snapshot.

For date-range searches without `--nipt`, the collector applies inclusive one-day chunking, emits one persisted snapshot per day, and stores resumable run state in the database. This keeps persistence keys coherent, avoids overlapping multi-day snapshots, makes capped `50`-row days visible in the run summary, and allows the same unfinished range to resume from the next unfinished day.

The only remaining Playwright path in the repo is the experimental notices collector.

If you run collectors from a shell with proxy variables set, those requests will honor the proxy environment by default. For local direct-connect runs, unset stale proxy variables before collecting.

QKB search dates are accepted on the CLI as `YYYY-MM-DD` and are converted to the page's `DD/MM/YYYY` form format for the HTTP requests the collector sends.

The QKB notices collector is intentionally kept in the repo as `qkb_notices_experimental`. It is exposed only through the `experimental` CLI group, is excluded from automated scheduler flows, preserves raw pages, and extracts likely document links. Its output should be treated as exploratory rather than authoritative.

If QKB changes selectors, update `config.py` or the collector methods rather than hard-coding brittle selectors in multiple places.
