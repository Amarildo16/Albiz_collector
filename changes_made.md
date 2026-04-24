# QKB Phase 1 Endpoint Discovery Prep Summary

Date: 2026-04-24

## Summary

- Prepared Phase 1 endpoint discovery for QKB historical extract PDFs.
- Added a manual discovery guide for capturing `document-handler.js` and browser Network evidence for historical, simple, and RPP document actions.
- Added a sanitized fixture staging README for future QKB document endpoint evidence.
- Added a pure offline parser for saved QKB search HTML document-action evidence.
- Added parser tests using the existing saved QKB search fixture.
- No endpoint URLs were guessed or marked confirmed from assumptions.
- No live scraping was performed.
- No real `.env` was created.

## Files Created Or Changed

- Created `QKB_ENDPOINT_DISCOVERY_GUIDE.md`.
- Created `tests/fixtures/qkb_documents/README.md`.
- Created `src/albiz_collector/sources/qkb_document_actions.py`.
- Created `tests/parsers/test_qkb_document_actions.py`.
- Rewritten `changes_made.md`.

## Parser Scope

- Extracts available `data-doc` values from saved QKB search HTML.
- Detects whether `fetchAndDisplayPDF` is referenced.
- Detects whether `downloadButtonPress` is referenced.
- Extracts the saved `fullUrl` value if present.
- Intentionally leaves `pdf_endpoint` as `None` because the final PDF endpoint is not present in the saved search HTML fixture.
- Performs no network requests.

## Tests

- Command run: `python -m pytest`
- Python: `3.12.9` from the project virtual environment.
- Result: `67 passed, 1 warning in 22.64s`.
- Warning: pytest could not create its cache path because of a generated `pytest-cache-files-*` access-denied temp directory. That generated temp directory was removed after the test run.

## Confirmed Non-Changes

- No production QKB collector behavior changed.
- No existing QKB search collection behavior changed.
- No database models changed.
- No Alembic migrations were created.
- No broad scraping or live endpoint requests were added.
- No endpoint is treated as confirmed unless it comes from a future saved JavaScript fixture or captured Network evidence.
