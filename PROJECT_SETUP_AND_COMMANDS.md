# Project Setup And Commands

This file is the practical command reference for running Albiz Collector from a fresh Git clone.

## Prerequisites

- Python 3.11 or newer.
- Git.
- A reachable MySQL or MariaDB database.
- Windows PowerShell for the commands below.

## Clone Project

```powershell
git clone <repository-url> Albiz_collector
Set-Location Albiz_collector
```

## Create Virtual Environment

```powershell
python -m venv .venv
```

## Activate Virtual Environment On Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

If script execution is blocked, allow scripts for the current process only:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
.\.venv\Scripts\Activate.ps1
```

## Install Dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The `requirements.txt` file installs the project in editable mode and uses runtime dependencies declared in `pyproject.toml`.

## Configure `.env`

```powershell
Copy-Item .env.example .env
```

Edit `.env` before running collectors. Important settings:

- `DATABASE_URL`: SQLAlchemy URL, for example `mysql+pymysql://root@localhost/albiz_collector`.
- `RAW_STORAGE_DIR`: raw artifact directory, default `./data/raw`.
- `HTTP_TIMEOUT_SECONDS`: HTTP timeout.
- `HTTP_USER_AGENT`: user agent sent to public sources.
- `APP_EXPORT_YEARS`: comma-separated APP export years.
- Scheduler variables if using `scheduler`.

Do not commit real `.env` values.

## Initialize Database / Run Migrations

Recommended for a fresh database:

```powershell
alembic upgrade head
```

Bootstrap alternative for local development only:

```powershell
python -m albiz_collector.cli init-db
```

`init-db` creates missing tables from the current SQLAlchemy models. It does not apply Alembic migrations or reconcile schema drift.

## Collect Data

APP exports:

```powershell
python -m albiz_collector.cli run app-exports
python -m albiz_collector.cli run app-exports --years 2025 --years 2026
```

QKB search by exact NIPT:

```powershell
python -m albiz_collector.cli run qkb-search --nipt M21528028T
```

QKB search by registration date range:

```powershell
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --forme-ligjore SHPK
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17 --restart
```

Targeted QKB lookup for known NIPT values:

```powershell
python -m albiz_collector.cli run qkb-search-by-nipt --nipt M21528028T
python -m albiz_collector.cli run qkb-search-by-nipt --input .\nipts.txt --limit 100 --delay-seconds 1
python -m albiz_collector.cli run qkb-search-by-nipt --input .\nipts.txt --limit 100 --dry-run
```

OpenCorporates financial enrichment:

```powershell
python -m albiz_collector.cli run opencorporates-financials --limit 100 --delay-seconds 1
python -m albiz_collector.cli run opencorporates-financials --nipt M21528028T --force
python -m albiz_collector.cli run opencorporates-financials --limit 100 --dry-run
```

## Normalize Data

```powershell
python -m albiz_collector.cli normalize app-exports
python -m albiz_collector.cli normalize qkb-search
python -m albiz_collector.cli normalize all
```

Normalization rebuilds normalized rows from stored structured snapshots and trusted raw artifacts.

## Generate Features

```powershell
python -m albiz_collector.cli features app
python -m albiz_collector.cli features qkb
python -m albiz_collector.cli features joined
python -m albiz_collector.cli features all
```

Feature commands rebuild company-level analytical tables from normalized rows.

## Run Profiling

```powershell
python -m albiz_collector.cli profile normalized
python -m albiz_collector.cli profile features
python -m albiz_collector.cli profile all
python -m albiz_collector.cli profile qkb-legal-forms
```

Profiling is read-only.

## Run Audits

```powershell
python -m albiz_collector.cli audit raw-fetches
python -m albiz_collector.cli audit raw-fetches --source-name qkb_search --limit 20
python -m albiz_collector.cli audit raw-fetches --corrupted-only
python -m albiz_collector.cli audit raw-fetches --mark-corrupted
python -m albiz_collector.cli audit qkb-search-runs
python -m albiz_collector.cli audit qkb-search-runs --status running --limit 20
```

Use `--mark-corrupted` only after reviewing the audit output.

## Run Smoke Checks

```powershell
python -m albiz_collector.cli smoke app
python -m albiz_collector.cli smoke qkb-search
python -m albiz_collector.cli smoke all
```

Smoke checks are live, low-volume source-contract checks for supported production sources.

## Scheduler

```powershell
python -m albiz_collector.cli scheduler
```

The scheduler runs APP exports daily and, when enabled in `.env`, QKB search over a rolling lookback window. Scheduler date calculations use `Europe/Tirane`.

## Useful Targeted Commands

Show CLI help:

```powershell
python -m albiz_collector.cli --help
python -m albiz_collector.cli run --help
python -m albiz_collector.cli run qkb-search --help
python -m albiz_collector.cli run qkb-search-by-nipt --help
python -m albiz_collector.cli run opencorporates-financials --help
```

Inspect migration state:

```powershell
alembic current
alembic history
```

Stamp an already matching existing database only when schema equivalence has been verified:

```powershell
alembic stamp head
```

## Experimental Commands

These commands exist under the `experimental` CLI group and are not part of the main thesis workflow.

```powershell
python -m albiz_collector.cli experimental qkb-notices
python -m albiz_collector.cli experimental qkb-notices --playwright
python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt M21528028T --doc-type historical --no-save
python -m albiz_collector.cli experimental qkb-legal-form-chunk-probe --date 2026-04-01
python -m albiz_collector.cli experimental qkb-secondary-chunk-probe --date 2026-04-01 --forme-ligjore SHPK
python -m albiz_collector.cli experimental opencorporates-financial-discovery --sample-size 10
```

Install Chromium only if running the experimental browser-assisted notices command:

```powershell
python -m playwright install chromium
```

The experimental document command is a one-NIPT probe. There is no active batch QKB document extraction workflow in the thesis implementation.

## Test Commands

Run the default test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run focused suites:

```powershell
python -m unittest discover -s tests\normalization -p "test_*.py" -v
python -m unittest discover -s tests\features -p "test_*.py" -v
python -m unittest discover -s tests\profiling -p "test_*.py" -v
python -m unittest discover -s tests\audit -p "test_*.py" -v
```

Run opt-in MySQL integration tests:

```powershell
$env:RUN_MYSQL_INTEGRATION_TESTS="1"
python -m unittest discover -s tests\integration -p "*_integration.py" -v
```
