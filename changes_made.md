# Config and Environment Update Summary

Date: 2026-04-24

## Summary
- Hardened config loading so `.env` is loaded explicitly from the repository root.
- Made relative filesystem config values deterministic from `PROJECT_ROOT`.
- Normalized relative SQLite database file URLs from `DATABASE_URL` against `PROJECT_ROOT`.
- Kept existing environment variable names and safe defaults.
- Did not create a real `.env`.

## Files Changed
- `src/albiz_collector/config.py`
- `.env.example`
- `README.md`
- `PROJECT_SETUP_AND_COMMANDS.md`
- `tests/test_config.py`
- `changes_made.md`

## Tests Added
- Added config tests proving:
  - config imports without a real `.env`
  - project-root `.env` is loaded even when the current working directory is elsewhere
  - relative `RAW_STORAGE_DIR` and relative SQLite file URLs resolve from project root
  - `.env.example` matches every environment variable read by `config.py`
  - `.env.example` can be loaded as a usable dotenv file

## Test Result
- Command: `python -m pytest`
- Environment: Python `3.12.9` from the existing `.venv`
- Result: `65 passed in 26.21s`

## Warnings and Intentional Non-Changes
- No scraper behavior, parser behavior, normalization logic, materialization logic, CLI command names, database models, schema, or Alembic migrations were changed.
- `.env.example` remains tracked; `.env` remains absent and ignored.
- Existing `.venv/` was left untouched.
- Generated pytest/cache/temp artifacts from verification were removed after the test run.
