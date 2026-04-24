# Project Setup and Commands

## 1. What This Guide Is For

This is the practical operator and developer runbook for this repository.

Use it when you need to:

- bring the repo onto a fresh machine
- choose a local-dev or production-like database path
- run migrations safely
- execute the supported collectors
- materialize normalized and feature tables
- profile the current dataset
- audit raw storage and QKB resumable run state
- troubleshoot real setup and runtime issues

This guide is based on the current code, migrations, tests, and CLI help. Where older repo docs disagree with current behavior, this guide follows the code.

## 2. Prerequisites

### Python

- Project metadata declares `requires-python = ">=3.11"`.
- The verified paths in this documentation pass used Python `3.12.9`.
- CI runs on Python `3.11` and `3.12`.
- A system Python `3.14.0` existed in this environment, but it was not the interpreter used for verification.

Practical recommendation:

- use Python `3.11` or `3.12`
- treat `3.14` as unverified unless you test it yourself

### Database

There are two realistic paths:

- MySQL:
  - this is the repo's current operational default
  - `.env.example` defaults to `mysql+pymysql://root@localhost/albiz_collector`
  - opt-in integration tests target MySQL
- SQLite:
  - used heavily in unit tests
  - verified in this documentation pass for migrations, normalization, features, profiling, audit, and a minimal live collection flow
  - useful for local bring-up and safe experimentation

Practical recommendation:

- use SQLite for the fastest local first run
- use MySQL for a production-like local environment

### Browser/runtime requirements

- No browser is required for the supported collectors.
- `python -m playwright install chromium` is only needed if you plan to run the experimental notices collector with `--playwright`.

### Network access

To use live collectors or smoke checks, the machine needs outbound access to:

- `www.app.gov.al`
- `format.qkb.gov.al`
- `qkb.gov.al` if you use the experimental notices path

### Proxy caveat

All live HTTP work uses `httpx` with `trust_env=True`.

That means these environment variables can break live commands if they point to a dead proxy:

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `ALL_PROXY`
- `NO_PROXY`
- lowercase equivalents

### Other system packages

No non-Python OS-level packages are clearly required by the supported path beyond whatever you normally use to install Python and, if desired, run MySQL locally.

## 3. Fresh Machine Setup

The commands below assume PowerShell on Windows, which matches the environment this repo was reviewed in.

### Step 1: Clone the repo

```powershell
git clone <your-repo-url> albiz_collector
cd albiz_collector
```

What this does:

- gets the code locally
- makes the repo root the working directory for all later commands

### Step 2: Create a virtual environment

```powershell
py -3.12 -m venv .venv
```

What this does:

- creates an isolated Python environment inside the repo

Why `3.12`:

- it matches the interpreter actually verified here
- it is covered by CI

### Step 3: Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

What this does:

- puts the venv's `python`, `pip`, and scripts first on your PATH for this shell

### Step 4: Upgrade pip

```powershell
python -m pip install --upgrade pip
```

What this does:

- ensures modern packaging behavior before dependency install

### Step 5: Install dependencies

```powershell
python -m pip install -r requirements.txt
```

What this does:

- installs the package in editable mode
- pulls runtime dependencies from `pyproject.toml`

Important detail:

- `requirements.txt` only contains `-e .`
- the real dependency list lives in `pyproject.toml`

### Step 6: Copy the environment template

```powershell
Copy-Item .env.example .env
```

What this does:

- creates a local `.env` file that `config.py` loads from the repository root
- gives you a private place to edit local database and storage settings
- keeps secrets and machine-specific paths out of Git because `.env` is ignored

### Step 7: Optional Playwright install

Only do this if you plan to use the experimental notices collector in browser-assisted mode.

```powershell
python -m playwright install chromium
```

### Step 8: Verify the Python and CLI you are actually using

```powershell
python --version
python -m albiz_collector.cli --help
python -m alembic heads
```

What should happen:

- `python --version` should show your venv interpreter, ideally `3.11.x` or `3.12.x`
- CLI help should list `run`, `experimental`, `normalize`, `features`, `profile`, `audit`, `smoke`, `scheduler`, and `init-db`
- Alembic should report head revision `9f2e4a8c1b6d`

If `python` still points somewhere unexpected:

- use `.\.venv\Scripts\python.exe` explicitly

## 4. Environment Configuration

### Runtime variables from `.env.example`

| Variable | Used by | Meaning | Notes |
| --- | --- | --- | --- |
| `APP_ENV` | settings load only | General environment label | Loaded but not used for runtime branching in current code. |
| `DATABASE_URL` | DB engine, Alembic, CLI | SQLAlchemy connection string | Most important setting. Current default is MySQL. Relative SQLite file URLs resolve against repo root. |
| `RAW_STORAGE_DIR` | collectors, storage helpers | Root directory for raw artifact files | Relative paths are resolved against repo root. |
| `HTTP_TIMEOUT_SECONDS` | `HttpClient` | Per-request timeout | Applies to live collectors and smoke checks. |
| `HTTP_USER_AGENT` | `HttpClient` | Outbound User-Agent header | Good place to put a real contact string if you operationalize this. |
| `APP_EXPORT_YEARS` | APP collector | Default year list when `run app-exports` is called without `--years` | Static list. It does not auto-expand when APP publishes a new year. |
| `APP_DOWNLOAD_ENABLED` | settings load only | Intended APP download toggle | Currently unused in collector code. Changing it has no effect today. |
| `QKB_NOTICES_PLAYWRIGHT_HEADLESS` | experimental notices collector | Headless browser flag | Experimental only. |
| `QKB_NOTICES_WAIT_MS` | experimental notices collector | Wait time after Playwright interaction | Experimental only. |
| `QKB_NOTICES_SEARCH_BUTTON_TEXT` | experimental notices collector | Text used when Playwright tries to click the notices search button | Experimental only. |
| `QKB_NOTICES_PARSE_DOCUMENT_LINKS_ONLY` | experimental notices collector | Whether to keep only document-like links | Experimental only. |
| `QKB_SEARCH_NIPT_SELECTOR` | smoke checks | CSS selector expected for the QKB NIPT field | Used by smoke checks, not by the HTTP collector itself. |
| `QKB_SEARCH_DATE_FROM_SELECTOR` | smoke checks | CSS selector expected for the QKB start-date field | Used by smoke checks, not by the HTTP collector itself. |
| `QKB_SEARCH_DATE_TO_SELECTOR` | smoke checks | CSS selector expected for the QKB end-date field | Used by smoke checks, not by the HTTP collector itself. |
| `QKB_NOTICES_DATE_FROM_SELECTOR` | settings load only | Intended notices date selector | Currently unused. |
| `QKB_NOTICES_DATE_TO_SELECTOR` | settings load only | Intended notices date selector | Currently unused. |
| `SCHEDULER_APP_EXPORTS_HOUR` | scheduler | Hour for daily APP collection | Minute is fixed at `00`. |
| `SCHEDULER_ENABLE_QKB_SEARCH` | scheduler | Enable or disable scheduled QKB search | `true` by default. |
| `SCHEDULER_QKB_SEARCH_HOUR` | scheduler | Hour for scheduled QKB search | Minute is fixed at `15`. |
| `SCHEDULER_QKB_SEARCH_LOOKBACK_DAYS` | scheduler | Inclusive lookback window size | `1` means scheduler runs from yesterday through today, inclusive, in `Europe/Tirane`. |

### Runtime variables not in `.env.example` but relevant

| Variable | Used by | Meaning |
| --- | --- | --- |
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and lowercase variants | `HttpClient` | Proxy environment honored by all live HTTP work |
| `RUN_MYSQL_INTEGRATION_TESTS` | integration tests only | Enables MySQL integration suite |
| `MYSQL_INTEGRATION_ADMIN_URL` | integration tests only | Admin connection used to create and drop disposable MySQL databases |

### Recommended local-dev `.env`

For the fastest verified local setup, use SQLite and keep your raw files separate from the repo's checked-in sample data:

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./local-dev.db
RAW_STORAGE_DIR=./data/raw-local
HTTP_TIMEOUT_SECONDS=30
HTTP_USER_AGENT=AlbizCollector/0.1 (+local-dev)
```

Why this is a good default:

- it avoids depending on a local MySQL server for the first run
- it avoids mixing your own runtime files into the repo's existing `data/raw/`
- it was verified during this documentation pass

### Recommended MySQL `.env`

For a production-like local path:

```dotenv
APP_ENV=development
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/albiz_collector
RAW_STORAGE_DIR=./data/raw-local
HTTP_TIMEOUT_SECONDS=30
HTTP_USER_AGENT=AlbizCollector/0.1 (+local-dev)
```

### Check the resolved runtime config

```powershell
python -c "from albiz_collector.config import settings; print(settings.database_url); print(settings.raw_storage_dir)"
```

What this does:

- shows the effective DB URL
- shows the resolved raw-storage path

## 5. Database Setup

### Fresh SQLite database path

If you use the local SQLite quickstart:

1. Set `DATABASE_URL=sqlite:///./local-dev.db` in `.env`.
2. Run:

```powershell
python -m alembic upgrade head
```

What this does:

- creates every application table
- creates `alembic_version`
- applies the baseline, quarantine, and QKB run-tracking revisions

This path was verified in this documentation pass.

### Fresh MySQL database path

If you use MySQL:

1. Create the database first using your normal DBA tooling.
2. A typical `mysql` CLI example is:

```powershell
mysql -u root -p -e "CREATE DATABASE albiz_collector CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

3. Set `DATABASE_URL` in `.env`.
4. Run:

```powershell
python -m alembic upgrade head
```

What this does:

- builds the full schema in MySQL
- creates `alembic_version`

Important note:

- this MySQL create-database example is standard DBA setup guidance
- it was not the database path verified in this documentation pass

### Existing database adoption path

Use this only if the database already matches the current schema exactly.

```powershell
python -m alembic stamp head
```

What this does:

- records the current Alembic head in `alembic_version`
- does not create or alter application tables

When to use it:

- you already have a database created from the current models
- you intentionally bootstrapped a local DB with `init-db` and want Alembic bookkeeping to start from the current head

When not to use it:

- you are not sure the DB matches the current schema
- the DB was created from an older version of the models
- you actually need schema changes applied

### Legacy bootstrap path

```powershell
python -m albiz_collector.cli init-db
```

What this does:

- creates missing tables for the current models
- does not run migrations
- does not manage schema evolution on an existing DB

Use it for:

- lightweight local bootstrap only

Do not treat it as a migration runner.

### Check migration state

```powershell
python -m alembic heads
python -m alembic current
```

What these do:

- `heads` shows the latest revision in the repo
- `current` shows the revision stamped into the current DB

## 6. Verification Commands

### CLI surface checks

```powershell
python -m albiz_collector.cli --help
python -m albiz_collector.cli run --help
python -m albiz_collector.cli run qkb-search --help
python -m albiz_collector.cli audit --help
python -m albiz_collector.cli smoke --help
```

Use these when:

- confirming the install worked
- checking the real current command surface instead of relying on older docs

### Alembic checks

```powershell
python -m alembic heads
python -m alembic current
```

Use these when:

- checking schema state before running collectors
- confirming a fresh DB is actually on head

### Environment sanity check

```powershell
python -c "from albiz_collector.config import settings; print(settings.database_url); print(settings.raw_storage_dir)"
```

Use this when:

- you are not sure which DB or raw-storage path the current shell will use

### What was verified here

These checks were actually run during this documentation pass:

- CLI help commands listed above
- `python -m alembic heads`
- `python -m alembic upgrade head` on disposable SQLite DBs
- `python -m alembic stamp head` on a disposable SQLite DB

## 7. Unit Tests

### Full unit suite

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

What it covers:

- parsers
- DB/bootstrap helpers
- normalization
- features
- profiling
- semantics
- audit
- utilities
- scheduler timezone behavior
- smoke-check evaluation logic
- QKB search collector behavior

When to run it:

- before committing
- after touching collectors, models, normalization, features, audit, smoke, or scheduler logic

Verification status:

- actually run in this documentation pass
- `61` tests passed

### Focused unit sub-suites

DB-focused:

```powershell
python -m unittest discover -s tests/db -p "test_*.py" -v
```

Normalization-focused:

```powershell
python -m unittest discover -s tests/normalization -p "test_*.py" -v
```

Use these when:

- you want a faster targeted check after touching DB or normalization code

## 8. Integration Tests

### Command

```powershell
$env:RUN_MYSQL_INTEGRATION_TESTS="1"
python -m unittest discover -s tests/integration -p "*_integration.py" -v
```

Optional admin URL override:

```powershell
$env:MYSQL_INTEGRATION_ADMIN_URL="mysql+pymysql://root:password@127.0.0.1:3306/mysql"
```

### What they require

- a reachable MySQL server
- a MySQL admin account that can create and drop databases
- `PyMySQL` already installed through project dependencies

### What they do

The integration suite creates disposable databases, then tests:

- `alembic upgrade head`
- `init_db` plus `alembic stamp head`
- core row persistence
- QKB normalization on real MySQL

### When to run them

- before production-like deployment changes
- after changing migrations
- after changing model definitions
- after changing persistence or normalization code

### Safety notes

- the tests are designed to create disposable DBs and drop them afterward
- they are opt-in and intentionally not part of the default unit run

### Verification status

- present in the repo
- not rerun in this documentation pass

## 9. Smoke Checks

### Commands

```powershell
python -m albiz_collector.cli smoke app
python -m albiz_collector.cli smoke qkb-search
python -m albiz_collector.cli smoke all
```

### What they verify

- APP:
  - index page is reachable
  - export years can still be parsed
  - expected `ExportDocument?year=` hint is still present
- QKB search:
  - page is reachable
  - a search form exists
  - expected form selectors still exist
  - a submit control exists

### What they do not verify

- they do not collect and store data
- they do not touch the DB
- they do not normalize anything
- they do not prove deeper parsing still works end to end

### When to use them

- before a production-like run
- after upstream site changes are suspected
- after changing collector assumptions
- when a live collector starts failing unexpectedly

### Proxy cleanup command

If live HTTP commands fail with connection-refused errors and you suspect dead proxy variables, clear them first:

```powershell
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY,Env:NO_PROXY,Env:http_proxy,Env:https_proxy,Env:all_proxy,Env:no_proxy -ErrorAction SilentlyContinue
```

### Verification status

- actually run in this documentation pass
- failed first because proxy vars pointed to `127.0.0.1:9`
- passed after those proxy vars were removed

## 10. Running the Supported Collectors

### 10.1 APP exports

Run all configured default years:

```powershell
python -m albiz_collector.cli run app-exports
```

Run specific years only:

```powershell
python -m albiz_collector.cli run app-exports --years 2025 --years 2026
```

What this command does:

- fetches the APP export index page
- saves that page to disk and `raw_fetches`
- downloads the requested yearly CSVs
- saves each CSV to disk and `raw_fetches`
- upserts one `structured_records` row per year

What tables and files it affects:

- raw files under `RAW_STORAGE_DIR/app_exports/...`
- `raw_fetches`
- `structured_records`

What to run next:

```powershell
python -m albiz_collector.cli normalize app-exports
python -m albiz_collector.cli features app
python -m albiz_collector.cli profile all
```

Verification status:

- actually run in this documentation pass on a disposable SQLite DB and disposable raw-storage directory

### 10.2 QKB search

Exact NIPT search:

```powershell
python -m albiz_collector.cli run qkb-search --nipt M21528028T
```

Date-range search:

```powershell
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
```

Restart the same unfinished date-range search from scratch:

```powershell
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --restart
```

What this command does:

- GETs the search page to establish cookies
- POSTs the search form payload
- saves raw HTML to disk and `raw_fetches`
- parses the inline JavaScript `response` payload
- upserts `structured_records`
- for non-NIPT date ranges:
  - runs one request per day
  - persists resumable progress in `qkb_search_runs`

What tables and files it affects:

- raw files under `RAW_STORAGE_DIR/qkb_search/...`
- `raw_fetches`
- `structured_records`
- `qkb_search_runs` for date-range searches without `--nipt`

How to read the output:

- `records_found` is the parsed row count
- `potentially_truncated_days` lists one-day windows that returned exactly `50` rows
- `run_id`, `run_status`, and `resume_from_date` matter only for non-NIPT date ranges

What to run next:

```powershell
python -m albiz_collector.cli normalize qkb-search
python -m albiz_collector.cli features qkb
python -m albiz_collector.cli profile all
```

Verification status:

- exact NIPT live path actually run in this documentation pass
- one-day date-range live path actually run in this documentation pass

## 11. Experimental Collector Usage

The experimental notices collector is intentionally separate from the supported flow.

Correct commands:

```powershell
python -m albiz_collector.cli experimental qkb-notices
python -m albiz_collector.cli experimental qkb-notices --playwright
```

What it does:

- saves the notices index page
- saves category pages
- extracts likely document links
- writes exploratory `structured_records`

What it does not do:

- no normalization
- no feature materialization
- no profiling
- no scheduler support
- no supported production guarantee

Important notes:

- if Playwright is unavailable, the collector falls back to HTTP mode
- `run_examples.txt` is stale and still shows `run qkb-notices`; that is no longer the correct CLI path

Verification status:

- code and tests were inspected
- this collector was not run live in this documentation pass

## 12. Normalization Commands

### Commands

```powershell
python -m albiz_collector.cli normalize app-exports
python -m albiz_collector.cli normalize qkb-search
python -m albiz_collector.cli normalize all
```

### What they do

- `normalize app-exports` fills or refreshes `normalized_app_export_rows`
- `normalize qkb-search` fills or refreshes `normalized_qkb_search_rows`
- `normalize all` runs both

### What tables they fill or update

- `normalized_app_export_rows`
- `normalized_qkb_search_rows`

### Rerun behavior

- normalization deletes existing rows for the same structured snapshot and reinserts them
- it does not append duplicates for the same snapshot

### Quarantine behavior

- if the referenced raw fetch is marked corrupted, that snapshot is skipped
- skipping a corrupted snapshot does not automatically delete already-existing normalized rows for that snapshot

### When to run normalization

- after collecting new snapshots
- after changing parser or normalization logic
- after adopting an older DB and wanting fresh derived rows

### Verification status

- actually run in this documentation pass on both empty and live-populated disposable SQLite DBs

## 13. Feature Materialization Commands

### Commands

```powershell
python -m albiz_collector.cli features app
python -m albiz_collector.cli features qkb
python -m albiz_collector.cli features joined
python -m albiz_collector.cli features all
```

### What they do

- `features app` rebuilds `app_company_features`
- `features qkb` rebuilds `qkb_company_features`
- `features joined` rebuilds `joined_company_features`
- `features all` runs all three

### What tables they fill or update

- `app_company_features`
- `qkb_company_features`
- `joined_company_features`

### Important behavior

- full-table rebuild, not incremental update
- rows tied to corrupted raw fetches are excluded indirectly through normalized-row filtering
- `features joined` can be empty even when APP and QKB feature tables are populated, because the join policy is exact NIPT equality only
- `features joined` does not require that `features app` or `features qkb` were run earlier; it rebuilds its own source aggregations from normalized rows

### When to run feature materialization

- after normalization
- after quarantining raw rows when you want derived feature tables refreshed
- after changing feature logic

### Verification status

- actually run in this documentation pass on empty and live-populated disposable SQLite DBs

## 14. Profiling Commands

### Commands

```powershell
python -m albiz_collector.cli profile normalized
python -m albiz_collector.cli profile features
python -m albiz_collector.cli profile all
```

### What they do

- `profile normalized` measures normalized row counts, missingness, identifier coverage, and exact join coverage
- `profile features` measures feature-table row counts, sparsity, and readiness
- `profile all` returns both plus an analytical-readiness summary

### How to interpret the output

Important fields in `profile normalized`:

- `row_counts`
- `winner_nipt_coverage`
- `business_nipt_coverage`
- `join_coverage`

Important fields in `profile features`:

- `row_counts`
- `feature_sparsity`
- `readiness`

Readiness statuses:

- `blocked`
- `usable_now`
- `usable_with_caution`

### What these commands do not do

- they do not mutate the DB
- they do not rebuild features
- they do not collect more data

### When to run them

- after normalization and feature materialization
- after quarantine if you want to measure the currently trusted subset
- before analytical work so you know what is actually populated

### Verification status

- actually run in this documentation pass on empty and live-populated disposable SQLite DBs

## 15. Audit / Quarantine Commands

### Raw-fetch integrity audit

Commands:

```powershell
python -m albiz_collector.cli audit raw-fetches
python -m albiz_collector.cli audit raw-fetches --source-name qkb_search --limit 25
python -m albiz_collector.cli audit raw-fetches --mark-corrupted
python -m albiz_collector.cli audit raw-fetches --corrupted-only
```

What it does:

- scans persisted raw artifacts
- reports missing files and content-hash mismatches
- optionally marks rows corrupted

What it does not do:

- no file deletion
- no file rewriting
- no hash rewriting

When to run it:

- after storage incidents
- after changing raw persistence logic
- before trusting historical raw artifacts
- when collectors or normalizers behave strangely

What to do after `--mark-corrupted`:

```powershell
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

Consider rerunning:

```powershell
python -m albiz_collector.cli normalize all
```

only when you also want fresh normalization stats or refreshed successful-snapshot materialization attempts.

### QKB resumable run audit

Commands:

```powershell
python -m albiz_collector.cli audit qkb-search-runs
python -m albiz_collector.cli audit qkb-search-runs --status failed
python -m albiz_collector.cli audit qkb-search-runs --limit 25
```

What it does:

- lists saved QKB date-range run rows
- shows current progress, status, timestamps, and last error

When to run it:

- after a failed date-range search
- before using `--restart`
- when you want to confirm whether the next invocation will resume or start fresh

### Verification status

- both audit command families were actually run in this documentation pass

## 16. Recommended Daily Workflow

For the supported flow, the practical daily sequence is:

1. Clear bad proxy variables if this shell inherits stale proxies.
2. If source drift is suspected, run:

```powershell
python -m albiz_collector.cli smoke all
```

3. Run supported collection:

```powershell
python -m albiz_collector.cli run app-exports
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-22 --data-ne 2026-04-23
```

4. If a QKB date-range run failed or was interrupted, inspect progress:

```powershell
python -m albiz_collector.cli audit qkb-search-runs
```

5. Rebuild normalized tables:

```powershell
python -m albiz_collector.cli normalize all
```

6. Rebuild features:

```powershell
python -m albiz_collector.cli features all
```

7. Profile the current dataset:

```powershell
python -m albiz_collector.cli profile all
```

8. Run `audit raw-fetches` intentionally when storage integrity is in doubt, not necessarily on every single daily run.

If you use the scheduler, remember:

- scheduler only performs step 3
- you still need steps 5 through 7 as separate operational tasks

## 17. Recommended Fresh-Environment Workflow

The fastest verified first-success path is the SQLite local-dev route.

### Verified local first-run sequence

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Then set at least these values in `.env`:

```dotenv
DATABASE_URL=sqlite:///./local-dev.db
RAW_STORAGE_DIR=./data/raw-local
```

Then run:

```powershell
python -m alembic upgrade head
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY,Env:NO_PROXY,Env:http_proxy,Env:https_proxy,Env:all_proxy,Env:no_proxy -ErrorAction SilentlyContinue
python -m albiz_collector.cli smoke all
python -m albiz_collector.cli run app-exports --years 2026
python -m albiz_collector.cli run qkb-search --nipt M21528028T
python -m albiz_collector.cli normalize all
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

What this gives you:

- verified DB schema
- verified live source reachability
- one APP snapshot
- one QKB search snapshot
- populated normalized tables
- populated APP and QKB feature tables if identifiers exist
- readiness output for the current local dataset

### Production-like fresh-environment sequence

Use the same order, but replace the SQLite DB setup with:

- create a MySQL database
- set `DATABASE_URL=mysql+pymysql://...`
- run `python -m alembic upgrade head`

## 18. Troubleshooting

### Import errors or `ModuleNotFoundError`

Symptom:

- `python -m albiz_collector.cli ...` cannot import the package

Likely cause:

- the venv is not active
- dependencies were not installed

Fix:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Wrong Python interpreter

Symptom:

- `python --version` shows an interpreter you did not intend to use
- packages seem installed but commands fail anyway

Likely cause:

- the shell is using system Python instead of the venv

Fix:

- reactivate the venv
- or call `.\.venv\Scripts\python.exe` explicitly

Important note:

- this environment had system Python `3.14.0`, but verification used the repo venv on `3.12.9`

### Database connection errors

Symptom:

- SQLAlchemy or Alembic cannot connect

Likely cause:

- bad `DATABASE_URL`
- MySQL server not running
- SQLite path not where you think it is

Fix:

```powershell
python -c "from albiz_collector.config import settings; print(settings.database_url)"
```

If you want the fastest no-MySQL path, switch to:

```dotenv
DATABASE_URL=sqlite:///./local-dev.db
```

### Migration mismatch

Symptom:

- Alembic says the DB is not on the expected revision
- app tables exist but `alembic_version` does not

Fix:

1. Back up the DB first.
2. Check:

```powershell
python -m alembic heads
python -m alembic current
```

3. If the DB is truly behind, run:

```powershell
python -m alembic upgrade head
```

4. If the DB already matches the current schema and only lacks Alembic bookkeeping, use:

```powershell
python -m alembic stamp head
```

Do not stamp blindly on an unknown old schema.

### Smoke checks or collectors fail with connection refused

Symptom:

- errors like `WinError 10061`

Likely cause:

- dead proxy environment variables

Fix:

```powershell
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY,Env:NO_PROXY,Env:http_proxy,Env:https_proxy,Env:all_proxy,Env:no_proxy -ErrorAction SilentlyContinue
```

Then rerun the smoke check or collector.

### `normalize all` reports zero snapshots

Symptom:

- normalization succeeds but sees no snapshots

Likely cause:

- collectors have not run yet
- `structured_records` is empty in the current DB
- you are pointed at the wrong `DATABASE_URL`

Fix:

- run the collectors first
- confirm the active DB URL

### `features all` returns empty or mostly empty tables

Symptom:

- feature row counts are zero or low

Likely causes:

- normalized tables are empty
- APP rows are missing `winner_nipt`
- QKB rows are missing `business_nipt`
- you rebuilt features before running normalization

Fix:

```powershell
python -m albiz_collector.cli normalize all
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

### `joined_company_features` is empty

Symptom:

- APP and QKB feature tables have rows, but joined features do not

Likely cause:

- exact `winner_nipt == business_nipt` matches do not exist in the current local dataset

This is expected behavior, not necessarily a bug.

Fix:

- collect QKB rows for actual APP winner NIPTs
- do not assume name-only joins should appear automatically

### Quarantine changed downstream outputs unexpectedly

Symptom:

- feature counts or profile results dropped after running `audit raw-fetches --mark-corrupted`

Likely cause:

- downstream code excludes rows tied to corrupted raw fetches

Fix:

```powershell
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

Remember:

- normalized rows for already-materialized corrupted snapshots may still physically exist in the normalized tables
- trusted downstream reads exclude them by filtering through `raw_fetches`

### `qkb-search --restart` is rejected

Symptom:

- CLI says `--restart` is not valid

Cause:

- `--restart` only works for QKB date-range searches without `--nipt`
- both `--data-nga` and `--data-ne` must be provided

### Manual SQLite query against `qkb_search_runs.current_date` looks wrong

Symptom:

- raw SQL returns today's date instead of the stored column value

Cause:

- SQLite has a built-in `current_date` function

Fix:

- quote the column name:

```sql
SELECT "current_date" FROM qkb_search_runs;
```

### `run_examples.txt` commands fail

Cause:

- that file is stale in the current repo state

Examples of stale content:

- `run qkb-notices` should now be `experimental qkb-notices`
- `run qkb-search --playwright` is no longer a valid supported command

Fix:

- trust current CLI help and the code, not that file

### `APP_DOWNLOAD_ENABLED` changes nothing

Cause:

- the setting exists but is currently unused in collector code

### Confusion about `collector.db`

Symptom:

- you see `collector.db` in the repo and assume SQLite is the active default

Reality:

- current default `DATABASE_URL` in code is MySQL
- the checked-in `collector.db` file is not the active default target unless you explicitly point `DATABASE_URL` at a SQLite file

## 19. Safe Operational Practices

- Back up the database before `python -m alembic upgrade head` or `python -m alembic stamp head`.
- Treat `init-db` as a local bootstrap tool, not as schema migration strategy.
- Keep supported and experimental flows separate. Do not treat the notices collector as production ingestion.
- Run smoke checks before production-like live runs or after suspected upstream site changes.
- Run `audit raw-fetches` after storage incidents or before trusting older collected artifacts.
- Rebuild features and rerun profiling after normalization changes or after quarantining raw rows.
- Do not rely on name-only joins for automated analysis; the code intentionally does not.
- Prefer a dedicated local raw-storage directory such as `./data/raw-local` so your own runs do not mix with checked-in sample artifacts.
- Avoid manual editing of raw files, hashes, and derived tables unless you are performing explicit recovery work and know the consequences.
- Use `python -m alembic` and `python -m albiz_collector.cli` from the active venv so you are sure which interpreter and environment are in play.

## 20. Quick Reference Command List

- Setup venv:
  - `py -3.12 -m venv .venv`
  - `.\.venv\Scripts\Activate.ps1`
- Install:
  - `python -m pip install --upgrade pip`
  - `python -m pip install -r requirements.txt`
- Optional Playwright:
  - `python -m playwright install chromium`
- Fresh schema:
  - `python -m alembic upgrade head`
- Adopt existing matching schema:
  - `python -m alembic stamp head`
- Check migration state:
  - `python -m alembic heads`
  - `python -m alembic current`
- Bootstrap only:
  - `python -m albiz_collector.cli init-db`
- CLI help:
  - `python -m albiz_collector.cli --help`
- Full unit suite:
  - `python -m unittest discover -s tests -p "test_*.py" -v`
- MySQL integration suite:
  - `$env:RUN_MYSQL_INTEGRATION_TESTS="1"`
  - `python -m unittest discover -s tests/integration -p "*_integration.py" -v`
- Smoke checks:
  - `python -m albiz_collector.cli smoke all`
- Clear proxy vars:
  - `Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY,Env:NO_PROXY,Env:http_proxy,Env:https_proxy,Env:all_proxy,Env:no_proxy -ErrorAction SilentlyContinue`
- APP collection:
  - `python -m albiz_collector.cli run app-exports`
  - `python -m albiz_collector.cli run app-exports --years 2026`
- QKB exact search:
  - `python -m albiz_collector.cli run qkb-search --nipt M21528028T`
- QKB date-range search:
  - `python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17`
- QKB date-range restart:
  - `python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --restart`
- Experimental notices:
  - `python -m albiz_collector.cli experimental qkb-notices`
  - `python -m albiz_collector.cli experimental qkb-notices --playwright`
- Normalize:
  - `python -m albiz_collector.cli normalize all`
- Features:
  - `python -m albiz_collector.cli features all`
- Profile:
  - `python -m albiz_collector.cli profile all`
- Raw-fetch audit:
  - `python -m albiz_collector.cli audit raw-fetches`
  - `python -m albiz_collector.cli audit raw-fetches --mark-corrupted`
- QKB run-state audit:
  - `python -m albiz_collector.cli audit qkb-search-runs`
- Scheduler:
  - `python -m albiz_collector.cli scheduler`
