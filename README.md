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
- `qkb_notices` remains experimental and is best treated as exploratory snapshot/link discovery, not a stable ingestion pipeline.

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

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1  # PowerShell
# source .venv/bin/activate   # bash/zsh
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env  # PowerShell
# cp .env.example .env       # bash/zsh
```

`requirements.txt` installs the package in editable mode and pulls runtime dependencies from `pyproject.toml`.

Initialize the database:

```bash
python -m albiz_collector.cli init-db
```

`init-db` is a schema bootstrap command for local development. It creates any missing tables for the current SQLAlchemy models, but it does not apply schema migrations to an existing database.

Current schema contract:
- new local databases can be bootstrapped with `init-db`
- existing databases are not auto-migrated when models change
- if the schema changes, recreate the local SQLite database or apply a manual migration before re-running `init-db`

Run the parser-focused test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run the DB-focused test suite:

```bash
python -m unittest discover -s tests/db -p "test_*.py" -v
```

Run the normalization-focused test suite:

```bash
python -m unittest discover -s tests/normalization -p "test_*.py" -v
```

Test layout:
- parser tests live in `tests/parsers/`
- DB tests live in `tests/db/`
- intentional fixture files live in `tests/fixtures/`
- runtime collector output under `data/raw/` is not part of the test suite

Run APP export collection:

```bash
python -m albiz_collector.cli run app-exports
```

Run QKB notices collection without browser automation (experimental snapshot mode):

```bash
python -m albiz_collector.cli run qkb-notices
```

Run QKB notices with Playwright (experimental browser-assisted snapshot mode):

```bash
python -m albiz_collector.cli run qkb-notices --playwright
```

Run QKB subject search (primary QKB path):

```bash
python -m albiz_collector.cli run qkb-search --nipt M21528028T
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
python -m albiz_collector.cli run qkb-search --nipt M21528028T --playwright
```

Materialize normalized datasets:

```bash
python -m albiz_collector.cli normalize app-exports
python -m albiz_collector.cli normalize qkb-search
python -m albiz_collector.cli normalize all
```

Start the scheduler:

```bash
python -m albiz_collector.cli scheduler
```

Scheduler intent:
- local recurring collection for the most useful baseline jobs
- `app_exports` is scheduled by default
- `qkb_search` is scheduled by default with a configurable rolling lookback window
- `qkb_notices` is experimental and is not scheduled by default; enable it explicitly via environment config if you want recurring exploratory runs

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

## Notes on QKB pages

The live QKB pages appear to be JS-driven / componentized. This repo therefore includes two collection modes where needed:
- **simple HTTP mode**: fetch + snapshot + basic anchor parsing,
- **Playwright mode**: open the page in Chromium, click the visible search button, then parse the post-render DOM.

The QKB subject-search collector uses the official search page by first performing a GET request to establish session cookies and then POSTing the form-urlencoded search payload back to the same endpoint. The returned HTML is persisted raw and the JavaScript `response` variable is decoded into a structured snapshot.

QKB search dates are accepted on the CLI as `YYYY-MM-DD` and are sent to both HTTP and Playwright flows in the same `YYYY-MM-DD` format.

The QKB notices collector is intentionally kept in the repo as an experimental collector. It preserves raw pages and extracts likely document links, but its output should be treated as exploratory rather than authoritative.

If QKB changes selectors, update `config.py` or the collector methods rather than hard-coding brittle selectors in multiple places.
