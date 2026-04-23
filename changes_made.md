# Changes Made

- Timestamp: `2026-04-23 16:00:48 +02:00`

## Files Changed
- `README.md`
- `FULL_AUDIT_REPORT.md`
- `changes_made.md`
- `docs/deployment_and_migration_runbook.md`
- `alembic/versions/2026_04_23_1540_9f2e4a8c1b6d_add_qkb_search_run_tracking.py`
- `src/albiz_collector/audit/__init__.py`
- `src/albiz_collector/audit/qkb_search_runs.py`
- `src/albiz_collector/cli.py`
- `src/albiz_collector/models.py`
- `src/albiz_collector/sources/qkb_search.py`
- `tests/db/test_schema_bootstrap.py`
- `tests/integration/mysql_runtime_flow_integration.py`
- `tests/sources/test_qkb_search_collection.py`

## Change Log
- Change: add a migration-backed `qkb_search_runs` table for persistent resumable date-range progress.
  - Files: `src/albiz_collector/models.py`, `alembic/versions/2026_04_23_1540_9f2e4a8c1b6d_add_qkb_search_run_tracking.py`, `tests/db/test_schema_bootstrap.py`, `tests/integration/mysql_runtime_flow_integration.py`
  - Reason: qkb-search daily runs needed database-backed progress tracking instead of file-based checkpoints.
  - Expected impact: date-range execution progress is now durable across process interruption, schema bootstrap includes the new table, and Alembic creates it safely on managed databases.
  - Commands/tests rerun:
    - `.venv\Scripts\python.exe -m unittest tests.db.test_schema_bootstrap -v`
    - `$env:RUN_MYSQL_INTEGRATION_TESTS='1'; .venv\Scripts\python.exe -m unittest discover -s tests\integration -p "*_integration.py" -v`

- Change: implement resumable qkb-search date-range execution with explicit restart support.
  - Files: `src/albiz_collector/sources/qkb_search.py`, `src/albiz_collector/cli.py`
  - Reason: the same unfinished qkb-search date range must resume from the next unfinished day instead of restarting silently from the beginning, while `--restart` must force a fresh run.
  - Expected impact: qkb-search now persists per-range run state, commits progress only after successful days, stops on the first failed day, resumes deterministically, and reports whether a run is starting new, resuming, or restarting from scratch.
  - Commands/tests rerun:
    - `.venv\Scripts\python.exe -m albiz_collector.cli run qkb-search --help`
    - `.venv\Scripts\python.exe -m unittest tests.sources.test_qkb_search_collection tests.parsers.test_qkb_search_parsing tests.normalization.test_qkb_search_normalization -v`
    - `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`

- Change: add an operator-facing audit view for saved qkb-search runs.
  - Files: `src/albiz_collector/audit/__init__.py`, `src/albiz_collector/audit/qkb_search_runs.py`, `src/albiz_collector/cli.py`
  - Reason: operators need a supported way to inspect resumable qkb-search run progress and last saved errors without querying the database manually.
  - Expected impact: `python -m albiz_collector.cli audit qkb-search-runs` now lists persisted qkb-search run rows and supports status/limit filters.
  - Commands/tests rerun:
    - `.venv\Scripts\python.exe -m albiz_collector.cli audit qkb-search-runs --help`

- Change: add focused qkb-search resume/restart tests and update operator docs.
  - Files: `tests/sources/test_qkb_search_collection.py`, `README.md`, `docs/deployment_and_migration_runbook.md`, `FULL_AUDIT_REPORT.md`, `changes_made.md`
  - Reason: the new run-state behavior needed deterministic test coverage and the repo docs needed to describe the real supported qkb-search workflow.
  - Expected impact: regressions in resumable run-state behavior are covered, and the README/runbook/audit report now document DB-backed resume, `--restart`, and run-state inspection.
  - Commands/tests rerun:
    - `.venv\Scripts\python.exe -m unittest tests.sources.test_qkb_search_collection -v`
    - `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`

## Final Verification Summary
- `.venv\Scripts\python.exe -m albiz_collector.cli run qkb-search --help` -> passed, includes `--restart`
- `.venv\Scripts\python.exe -m albiz_collector.cli audit qkb-search-runs --help` -> passed
- `.venv\Scripts\python.exe -m unittest tests.sources.test_qkb_search_collection tests.db.test_schema_bootstrap -v` -> `11/11` passed
- `.venv\Scripts\python.exe -m unittest tests.parsers.test_qkb_search_parsing tests.normalization.test_qkb_search_normalization -v` -> `8/8` passed
- `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` -> `61/61` passed
- `$env:RUN_MYSQL_INTEGRATION_TESTS='1'; .venv\Scripts\python.exe -m unittest discover -s tests\integration -p "*_integration.py" -v` -> `3/3` passed
