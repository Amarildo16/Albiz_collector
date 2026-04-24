# QKB Experimental Document Fetcher Hardening Summary

Date: 2026-04-24

## Summary

- Hardened the experimental one-NIPT QKB document fetcher with confirmed browser replay headers.
- Updated request headers to include:
  - `Accept: */*`
  - `Content-Type: application/x-www-form-urlencoded`
  - `Origin: https://format.qkb.gov.al`
  - `Referer: https://format.qkb.gov.al/kerko-per-subjekt/`
- Updated fake-HTTP tests to assert the full confirmed header set.
- Updated the historical request fixture with sanitized browser cookie evidence.
- Updated discovery documentation to note that browser evidence sent cookie name `TS2f08e597027`, while the experimental CLI one-NIPT fetch worked without manually supplying cookies.

## Files Changed

- `src/albiz_collector/sources/qkb_documents.py`
- `tests/sources/test_qkb_documents.py`
- `tests/fixtures/qkb_documents/historical-view-request.json`
- `QKB_ENDPOINT_DISCOVERY_GUIDE.md`
- `changes_made.md`

## Warnings And Intentional Non-Changes

- No production QKB search collector behavior changed.
- No batch or broad QKB document collection was added.
- No database models changed.
- No Alembic migrations were created.
- No raw cookie values or session tokens were stored.
- No real `.env` was created or modified.
- Existing local `.env` and modified `.env.example` were left untouched.

## Test Result

- Command run: `python -m pytest`
- Python: `3.12.9` from the project virtual environment.
- Result: `77 passed, 1 warning in 32.04s`.
- Warning: pytest could not create its cache path under `.pytest_cache`; the generated cache directory was removed after the test run.
