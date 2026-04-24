# Experimental QKB One-NIPT Document Fetch Summary

Date: 2026-04-24

## Summary

- Added a very limited experimental one-NIPT QKB document fetch path using confirmed endpoint evidence only.
- Implemented request payload validation for confirmed document types: `historical`, `simple`, and `rpp`.
- Implemented POST handling for the confirmed `search-for-subject-get-documents.php` endpoint.
- Implemented JSON parsing even when the response content type is `text/html; charset=UTF-8`.
- Implemented backend status interpretation:
  - `status > 0`: success.
  - `status == 0`: not found.
  - `status < 0`: server error.
- Implemented base64 PDF decoding and `%PDF` magic validation.
- Added optional RawFetch storage for a single successful decoded PDF through source `qkb_documents`.
- Added an experimental CLI command for one document only:
  - `python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt <NIPT> --doc-type historical`
- No endpoint URLs were guessed.
- No live scraping was performed during tests.
- No real `.env` was created.

## Files Created Or Changed

- Created `src/albiz_collector/sources/qkb_documents.py`.
- Updated `src/albiz_collector/cli.py`.
- Created `tests/sources/test_qkb_documents.py`.
- Created `tests/fixtures/qkb_documents/historical-view-request.json`.
- Updated `tests/fixtures/qkb_documents/README.md`.
- Updated `QKB_ENDPOINT_DISCOVERY_GUIDE.md`.
- Rewritten `changes_made.md`.

## Tests Added

- Request payload construction for `historical`, `simple`, and `rpp`.
- Invalid document type rejection.
- Confirmed endpoint POST call shape with fake HTTP responses.
- Successful JSON response with `text/html; charset=UTF-8` content type.
- Base64 PDF decoding and `%PDF` validation.
- `status == 0` not-found handling.
- `status < 0` server-error handling.
- Malformed JSON rejection.
- Successful JSON with non-PDF base64 rejection.
- Optional RawFetch storage for a successful single PDF.
- Experimental CLI help coverage.

## Test Result

- Command run: `python -m pytest`
- Python: `3.12.9` from the project virtual environment.
- Result: `77 passed, 1 warning in 23.28s`.
- Warning: pytest could not create its cache path because of a generated `pytest-cache-files-*` access-denied temp directory. The generated temp directory was removed after the test run.

## Intentional Non-Changes

- No batch or broad QKB document collection was implemented.
- No existing production QKB search collector behavior changed.
- No database models changed.
- No Alembic migrations were created.
- No normalized financial facts were added.
- No raw cookies or session tokens are stored.
- The experimental CLI command fetches at most one requested NIPT/document type per invocation.
