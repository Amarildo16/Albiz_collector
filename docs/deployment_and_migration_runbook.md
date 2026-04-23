# Deployment And Migration Runbook

This runbook describes the supported operational path for the repository in its current state.

## Scope

Supported production collectors:
- `app_exports`
- `qkb_search`

Not part of the supported production workflow:
- `qkb_notices_experimental`

This runbook assumes Alembic migrations are the required path for schema changes.

## Safe Default Production Flow

1. Configure environment:
   - set `DATABASE_URL`
   - set `RAW_STORAGE_DIR`
   - set supported scheduler variables if you use the scheduler
2. Back up the target database before applying any migration.
3. Ensure the target DB is on the expected Alembic revision.
4. Run supported collectors only:
   - `python -m albiz_collector.cli run app-exports`
   - `python -m albiz_collector.cli run qkb-search --...`
   - or `python -m albiz_collector.cli scheduler`
5. Rebuild derived tables from stored snapshots:
   - `python -m albiz_collector.cli normalize all`
   - `python -m albiz_collector.cli features all`
   - `python -m albiz_collector.cli profile all`

## Fresh Database Setup

For a brand-new database:

```bash
alembic upgrade head
```

This is the supported path for creating the full schema, including `alembic_version`.

After a fresh DB is ready, you can run the supported collectors and then materialize the derived layers:

```bash
python -m albiz_collector.cli run app-exports
python -m albiz_collector.cli normalize all
python -m albiz_collector.cli features all
python -m albiz_collector.cli profile all
```

## Existing Database Adoption

If you already have a database created from the current models and it matches the current schema exactly:

1. Back it up first.
2. Record the existing schema state manually.
3. Stamp the current Alembic head without recreating tables:

```bash
alembic stamp head
```

Use `stamp head` only when you are confident the existing schema already matches the current migration head.

If the existing schema does not match the current migration history, do not stamp blindly. Resolve the schema gap first.

## Migration Execution

Before any migration:
- take a database backup
- review the generated Alembic revision
- prefer applying migrations first in a disposable or staging environment

Create and apply a migration:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

## Backup Expectation Before Migrations

This repo does not provide automated backup tooling.

Operational expectation:
- create a database backup before `alembic upgrade head`
- keep the backup until the deployment is verified
- do not rely on `downgrade` as your only recovery path

## Rollback Expectation And Limitations

Rollback is limited by the migrations you have actually written and tested.

Current safe expectation:
- if a downgrade revision exists and has been tested, you may use it intentionally
- otherwise, restore from a backup instead of improvising schema rollback in production

For data-affecting incidents, restoring from backup is safer than trying to reconstruct state manually.

## Operational Commands

### `audit raw-fetches`

Use when:
- validating historical raw provenance
- investigating collector/storage incidents
- after changes to raw persistence logic
- before trusting older stored artifacts for downstream analysis

Commands:

```bash
python -m albiz_collector.cli audit raw-fetches
python -m albiz_collector.cli audit raw-fetches --source-name qkb_search
python -m albiz_collector.cli audit raw-fetches --mark-corrupted
python -m albiz_collector.cli audit raw-fetches --corrupted-only
```

Important:
- the command does not delete rows
- the command does not rewrite files
- the command does not rewrite stored hashes
- `--mark-corrupted` only sets quarantine metadata on affected rows

### `normalize all`

Use when:
- new supported source snapshots have been collected
- parser/normalizer logic changed and you need refreshed normalized rows
- you want to confirm the current normalized state after a maintenance pass

Command:

```bash
python -m albiz_collector.cli normalize all
```

Current behavior note:
- normalization skips quarantined raw fetches
- it does not itself purge previously materialized rows automatically for already-quarantined snapshots unless those snapshots are reprocessed successfully

### `features all`

Use when:
- normalized rows changed
- quarantined raw rows should be excluded from feature rebuilds
- you want the current feature tables to reflect the latest trusted normalized input

Command:

```bash
python -m albiz_collector.cli features all
```

### `profile all`

Use when:
- you want the current analytical-readiness snapshot
- you have just rebuilt features
- you want to inspect current join coverage and sparsity after maintenance

Command:

```bash
python -m albiz_collector.cli profile all
```

## MySQL Integration Tests

These are opt-in and intentionally separate from the fast default unit suite.

Use when:
- verifying the supported MySQL runtime path locally
- validating migration behavior against a real MySQL server
- checking that persistence and normalization still work before deployment
- validating the optional CI MySQL job

Commands:

```bash
$env:RUN_MYSQL_INTEGRATION_TESTS="1"  # PowerShell
python -m unittest discover -s tests/integration -p "*_integration.py" -v
```

Optional admin URL override:
- `MYSQL_INTEGRATION_ADMIN_URL=mysql+pymysql://root:password@127.0.0.1:3306/mysql`

The integration suite creates disposable databases and drops them after the run.

## Source-Contract Smoke Checks

These are opt-in live checks for the supported production sources only:
- APP export index page
- QKB search page

Use when:
- before a production rollout
- after upstream site changes are suspected
- after collector selector/contract changes
- when a supported collector suddenly starts failing live

Commands:

```bash
python -m albiz_collector.cli smoke app
python -m albiz_collector.cli smoke qkb-search
python -m albiz_collector.cli smoke all
```

Behavior:
- low-volume
- read-only
- does not touch the database
- fails clearly when expected structural contract elements disappear

If your shell has stale proxy environment variables set, unset them first or the smoke checks may fail for network reasons rather than real source drift.

## Scheduler Use

Supported scheduler scope:
- `app_exports`
- `qkb_search`

The scheduler uses `Europe/Tirane` explicitly for its rolling QKB search window.
QKB date-range runs persist resumable progress in the database and resume from the next unfinished day when the same unfinished range is invoked again.

Experimental collectors are intentionally excluded from automated scheduler flows.

## Optional Maintenance Actions

Optional maintenance, depending on the incident or deployment:
- `audit raw-fetches --mark-corrupted`
- `audit qkb-search-runs`
- `normalize all`
- `features all`
- `profile all`
- opt-in smoke checks
- opt-in MySQL integration tests

These are not all required on every run. Use them intentionally based on what changed.

## Experimental Collector Path

The experimental path remains available for explicit manual use only:

```bash
python -m albiz_collector.cli experimental qkb-notices
python -m albiz_collector.cli experimental qkb-notices --playwright
```

It is not part of the supported production flow.
It is not part of the supported scheduler flow.
It should not be treated as a production ingestion pipeline.
