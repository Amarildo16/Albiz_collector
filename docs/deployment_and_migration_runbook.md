# Deployment And Migration Runbook

This runbook describes the supported operational path for the current repository.

## Supported Production Workflow

Production commands:

- `run app-exports`
- `run qkb-search`
- `run qkb-search-by-nipt`
- `run opencorporates-financials`
- `normalize all`
- `features all`
- `profile all`
- `audit raw-fetches`
- `audit qkb-search-runs`
- `smoke app`
- `smoke qkb-search`
- `smoke all`
- `scheduler`

Experimental commands are available only under `experimental` and are not part of the production thesis workflow.

## Fresh Database Setup

For a new database:

```powershell
alembic upgrade head
```

Then collect and materialize:

```powershell
python -m albiz_collector.cli run app-exports
python -m albiz_collector.cli run qkb-search --data-nga 2026-04-01 --data-ne 2026-04-17
python -m albiz_collector.cli normalize all
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

## Existing Database Adoption

If an existing database already matches the current migration head exactly, stamp it only after manual schema verification:

```powershell
alembic stamp head
```

Do not use `stamp head` to hide schema drift.

## Migration Execution

Before applying migrations:

- back up the database;
- review the migration file;
- test against a disposable or staging database where possible.

Apply migrations:

```powershell
alembic upgrade head
```

Create a new migration only when making schema changes:

```powershell
alembic revision --autogenerate -m "describe schema change"
```

## Raw-Fetch Audit

Use raw-fetch audit before trusting older raw artifacts or after storage-related incidents:

```powershell
python -m albiz_collector.cli audit raw-fetches
python -m albiz_collector.cli audit raw-fetches --source-name qkb_search
python -m albiz_collector.cli audit raw-fetches --corrupted-only
python -m albiz_collector.cli audit raw-fetches --mark-corrupted
```

`--mark-corrupted` sets quarantine metadata. It does not delete rows or rewrite files.

## QKB Run-State Audit

Use QKB run-state audit to inspect resumable date-range runs:

```powershell
python -m albiz_collector.cli audit qkb-search-runs
python -m albiz_collector.cli audit qkb-search-runs --status running --limit 20
```

## Derived Table Rebuild

After collection or parser changes:

```powershell
python -m albiz_collector.cli normalize all
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

## Smoke Checks

Smoke checks are opt-in live checks for supported public source contracts:

```powershell
python -m albiz_collector.cli smoke app
python -m albiz_collector.cli smoke qkb-search
python -m albiz_collector.cli smoke all
```

They are low-volume and do not write database rows.

## Scheduler

Run:

```powershell
python -m albiz_collector.cli scheduler
```

The scheduler runs APP exports and, when enabled in `.env`, a rolling QKB search window. Scheduler date logic uses `Europe/Tirane`.

## Tests

Default suite:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Opt-in MySQL integration suite:

```powershell
$env:RUN_MYSQL_INTEGRATION_TESTS="1"
python -m unittest discover -s tests\integration -p "*_integration.py" -v
```

## Experimental Commands

These commands are not part of the production thesis workflow:

```powershell
python -m albiz_collector.cli experimental qkb-notices
python -m albiz_collector.cli experimental qkb-notices --playwright
python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt M21528028T --doc-type historical --no-save
python -m albiz_collector.cli experimental qkb-legal-form-chunk-probe --date 2026-04-01
python -m albiz_collector.cli experimental qkb-secondary-chunk-probe --date 2026-04-01 --forme-ligjore SHPK
python -m albiz_collector.cli experimental opencorporates-financial-discovery --sample-size 10
```

The experimental document command is a bounded one-NIPT probe. No batch QKB document workflow is part of deployment.
