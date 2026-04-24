# QKB Historical Extract / Financial Document Collection Design

Date: 2026-04-24

## Scope And Current State

This is a design-only document. It does not add collector behavior, schema changes, migrations, parser changes, normalization changes, CLI commands, or live scraping.

Current repository state assumed for this design:

- Repository cleanup is complete.
- Environment/config loading has been hardened.
- `.env.example` remains tracked and no real `.env` should be created.
- The current test baseline is expected to pass on Python 3.12.
- Existing QKB search results already provide NIPT values that can seed later document collection.

## Files Inspected

- `src/albiz_collector/sources/qkb_search.py`
- `src/albiz_collector/sources/base.py`
- `src/albiz_collector/sources/qkb_notices_experimental.py`
- `src/albiz_collector/normalization/qkb_search.py`
- `src/albiz_collector/utils/storage.py`
- `src/albiz_collector/utils/raw_fetches.py`
- `src/albiz_collector/models.py`
- `src/albiz_collector/cli.py`
- `tests/fixtures/qkb_search/search-results-with-records.html`
- `tests/fixtures/qkb_notices/category-page.html`
- `tests/fixtures/normalization/qkb_search_snapshot_payload.json`
- `tests/parsers/test_qkb_search_parsing.py`
- `tests/parsers/test_qkb_notices_parsing.py`
- `tests/sources/test_qkb_search_collection.py`
- `tests/normalization/test_qkb_search_normalization.py`
- `tests/audit/test_raw_fetch_integrity.py`
- `tests/utils/test_storage.py`
- `README.md`
- `PROJECT_SETUP_AND_COMMANDS.md`

Search terms used across the codebase included `historical`, `extract`, `ekstrakt`, `fetchAndDisplayPDF`, `downloadButtonPress`, `pdf`, `rpp`, `nipti`, and `modal`.

## Existing QKB Pipeline Summary

`QkbSearchCollector` in `src/albiz_collector/sources/qkb_search.py` is the production QKB search collector. It:

- Uses `source_name = "qkb_search"`.
- Establishes a QKB search session with a GET to `settings.qkb_search_url`.
- POSTs search form data to `settings.qkb_search_url`.
- Supports direct NIPT search and date-window search.
- Splits date ranges into daily chunks for resumable collection.
- Persists daily range progress in `QkbSearchRun`.
- Saves raw HTML search pages through `CollectorBase.save_raw_fetch` using `fetch_kind="search_results_page"`.
- Extracts the frontend `response` JavaScript value from saved HTML.
- Persists parsed snapshots as `StructuredRecord` rows with `record_type="qkb_search_snapshot"`.

`src/albiz_collector/normalization/qkb_search.py` materializes `StructuredRecord.payload["response"]` into `NormalizedQkbSearchRow`, including `business_nipt`, names, legal form, registration date, city, status, activity, ownership text, admin/shareholder text, red-flag status, and the original source payload.

Raw artifact storage already has useful primitives:

- `CollectorBase.save_raw_fetch` computes SHA-256 content hashes.
- PDF file extensions are already inferred when the URL ends in `.pdf` or the content type contains `pdf`.
- `build_storage_path` stores raw files under `settings.raw_storage_dir / source / YYYY / MM / DD / fetch_kind / filename`.
- `RawFetch` stores source URL, fetch kind, content hash, storage path, status code, content type, and extra metadata.
- Raw fetch integrity helpers can detect missing, corrupted, or hash-mismatched files.

`qkb_notices_experimental` is exploratory and separate from the production QKB search flow. It parses likely document links from notice pages but does not prove QKB search modal document endpoints.

## Exact Fixture Evidence

Primary fixture: `tests/fixtures/qkb_search/search-results-with-records.html`.

Confirmed search form evidence:

- The search form has `id="searchForm"`, `method="post"`, and an empty `action`.
- Hidden sort fields exist: `orderColumn` and `orderDir`.
- Search input names include `nipt`, `emriISubjektit`, `emriTregtar`, `formeLigjore`, `pronesia`, `dataNga`, `dataNe`, `numriId`, `administrator`, `aksionerOrtak`, `sektoriIVeprimtarise`, `qarku`, `qyteti`, and `adresa`.
- No CSRF, nonce, or token input was found in the saved fixture.

Confirmed modal evidence:

- The detail modal has `id="detailModal"` and title text for subject details.
- The selected record NIPT is rendered into a modal field with `data-field="nipti"`.
- The document action area has `id="viewAndDownload"` and document pills under `id="docPills"`.
- Three document types are represented by `data-doc` values:
  - `rpp`, labeled as an RPP extract.
  - `simple`, labeled as a simple extract.
  - `historical`, labeled as a historical extract.
- Each document type has a viewer pill and a download button.
- The modal contains `pdfSpinner` and an `iframe` with `id="pdfViewer"`.
- Hidden or rendered red-flag placeholders include `rppRedFlagText`, `bilanciRedFlagText`, and `adminRedFlagText`.

Confirmed JavaScript evidence:

- The fixture loads external JavaScript from:
  - `.../subject/document-handler.js`
  - `.../subject/indexed-db-handler.js`
  - `.../subject/components/search-form/search-form.js`
  - `.../subject/components/validation/form-validation.js`
- The fixture sets `fullUrl` to:
  - `https://format.qkb.gov.al/wp-content/themes/twentytwentyfive-child/modules/search/national-registry/subject/`
- The fixture embeds QKB search results in `response = JSON.parse(...)`.
- The embedded result records include `nipti`, `rppRedFlagText`, `bilanciRedFlagText`, `adminRedFlagText`, and `showRedFlag`.
- `GetFlagData(fullUrl, nipt)` is defined inline and POSTs `nipt=<value>` as `application/x-www-form-urlencoded` to:
  - `search-for-subject-get-red-flag.php`
- When the user opens a subject detail modal, the code sets `currentRec = rec` and calls `GetFlagData(fullUrl, rec["nipti"])`.
- Viewer pill clicks call:
  - `fetchAndDisplayPDF(currentRec.nipti, docType, fullUrl)`
- Download button clicks call:
  - `downloadButtonPress(currentRec.nipti, docType, fullUrl)`
- The inline fixture code does not define `fetchAndDisplayPDF` or `downloadButtonPress`; those functions are expected to come from external `document-handler.js`.

Confirmed financial-statement signal:

- `bilanciRedFlagText` appears in the embedded response and in the red-flag popover content.
- No separate `data-doc="bilanci"` or financial-statement download button was found in the saved QKB search fixture.

## Endpoint Evidence Boundary

The saved fixture confirms the frontend document types and the JavaScript function calls, but it does not confirm the final PDF endpoint.

Confirmed:

- Base frontend module path: `https://format.qkb.gov.al/wp-content/themes/twentytwentyfive-child/modules/search/national-registry/subject/`
- Red-flag endpoint: `search-for-subject-get-red-flag.php`
- Red-flag request method and payload: POST form body with `nipt`.
- Document action parameters passed by the frontend: `nipti`, `docType`, and `fullUrl`.

Unknown and requiring live/manual verification:

- The exact PDF endpoint or endpoints used by `fetchAndDisplayPDF`.
- The exact download endpoint or endpoints used by `downloadButtonPress`.
- Whether document requests use GET or POST.
- Whether payload fields are named `nipt`, `nipti`, `docType`, `type`, or something else.
- Whether cookies or a session initialized by the QKB search page are required.
- Whether request headers beyond standard browser headers are required.
- Whether responses are always PDFs or sometimes JSON/HTML error pages.
- Whether `simple`, `historical`, and `rpp` map directly to backend document type values.
- Whether financial statements are exposed by the same document handler or only signaled through `bilanciRedFlagText`.
- Whether a missing document is represented as HTTP 404, a JSON status, an HTML alert, or a zero-byte/placeholder PDF.

No production code should assume a final PDF URL until `document-handler.js` and browser network traffic have been captured and saved as fixtures.

## Proposed New Module Structure

Future implementation should be additive and isolated from existing production search collection:

- `src/albiz_collector/sources/qkb_documents.py`
  - Future collector for QKB subject documents.
  - Starts behind an experimental CLI command until endpoint behavior is proven.
  - Reuses existing HTTP client/session and `CollectorBase.save_raw_fetch`.
- `src/albiz_collector/sources/qkb_document_actions.py`
  - Pure parser/discovery helpers for extracting modal document actions from saved HTML/JS fixtures.
  - Should be unit-testable without network access.
- `src/albiz_collector/documents/pdf_text.py`
  - Future PDF text extraction adapter.
  - Should accept local raw PDF paths and return deterministic text/extraction metadata.
- `src/albiz_collector/normalization/qkb_documents.py`
  - Future normalized document metadata and text-derived facts.
- `src/albiz_collector/features/qkb_financials.py`
  - Future research features derived from normalized financial facts.

This structure keeps endpoint discovery, raw document collection, PDF parsing, normalization, and research features separate.

## Proposed Raw PDF Storage Strategy

Use `RawFetch` as the canonical raw artifact record for downloaded PDFs.

Proposed source and fetch kinds:

- `source_name`: `qkb_documents`
- `fetch_kind`: one of:
  - `simple_extract_pdf`
  - `historical_extract_pdf`
  - `rpp_pdf`
  - `financial_statement_pdf` only after evidence confirms such documents exist and how they are requested.

Proposed file naming:

- Include normalized NIPT and document type in the URL-derived or explicit filename stem.
- Continue using existing content-hash-based filenames from `CollectorBase.save_raw_fetch`.
- Avoid overwriting prior versions when a document changes.

Proposed `RawFetch.extra_metadata`:

- `business_nipt`
- `document_type`
- `request_fingerprint`
- `request_method`
- `request_payload`
- `discovery_source`
- `discovery_raw_fetch_id`
- `qkb_search_structured_record_id`
- `content_disposition`
- `response_content_type`
- `response_content_length`
- `verified_pdf_magic`
- `document_handler_js_hash`
- `manual_verification_notes` during Phase 1 only

Before saving as a PDF, the collector should verify that the response body begins with `%PDF` or that another trusted PDF validation layer accepts it. HTML and JSON error bodies should be saved with an error fetch kind or recorded as failed metadata, not silently treated as PDFs.

## Proposed Metadata Model / Table Design

Do not implement this until endpoint discovery is complete.

Proposed table: `qkb_document_fetches`

Candidate columns:

- `id`
- `business_nipt`
- `document_type`
- `source_name`
- `source_url`
- `request_method`
- `request_payload_json`
- `request_fingerprint`
- `http_status_code`
- `response_content_type`
- `response_content_length`
- `content_hash`
- `raw_fetch_id`
- `storage_path`
- `status`
- `error_code`
- `error_message`
- `first_seen_at`
- `last_seen_at`
- `fetched_at`
- `is_current`
- `endpoint_evidence_version`
- `created_at`
- `updated_at`

Suggested constraints and indexes:

- Unique active request key on `(business_nipt, document_type, request_fingerprint)`.
- Unique content key on `(business_nipt, document_type, content_hash)`.
- Index on `(business_nipt, document_type, fetched_at)`.
- Foreign key from `raw_fetch_id` to `raw_fetches.id`.

Candidate statuses:

- `discovered`
- `fetched`
- `not_found`
- `not_pdf`
- `temporarily_failed`
- `permanently_failed`
- `superseded`

The table should describe document fetch attempts and versions. It should not duplicate the full raw PDF bytes, and it should not replace `RawFetch`.

## Idempotency Rules

- Normalize NIPT values before work is queued: trim whitespace and use a single canonical casing.
- Use an allowlist of document types: `simple`, `historical`, `rpp` initially.
- Build a request fingerprint from method, endpoint path, normalized payload, document type, and any confirmed required static parameters.
- If a completed row exists for the same NIPT, document type, and request fingerprint, skip by default.
- If a refetch is explicitly requested, fetch again but dedupe by content hash.
- If the same content hash is returned for the same NIPT and document type, update `last_seen_at` without creating a duplicate logical version.
- If a new content hash is returned for the same NIPT and document type, create a new version and mark the previous version non-current or superseded.
- Persist failures with enough metadata to avoid tight retry loops.
- Keep all phases resumable from persisted state.

## Deduplication Strategy

Use SHA-256 of the exact response bytes as the primary content identity.

Deduplication should happen at two levels:

- Raw artifact level: the same bytes should produce the same `RawFetch.content_hash`.
- Logical document level: the same NIPT, document type, and content hash should not create duplicate document metadata rows.

Different NIPTs returning identical PDFs should not be collapsed into one logical document row unless later evidence proves the file is a generic placeholder. Cross-NIPT duplicate hashes should be flagged for audit because they may indicate error PDFs or placeholder responses.

## Retry And Rate-Limit Strategy

Start conservatively:

- Phase 1 should use one manually selected NIPT.
- Use one request at a time.
- Add a fixed delay between document requests.
- Retry only transient failures: timeouts, connection errors, HTTP 429, and HTTP 5xx.
- Do not retry confirmed 404/not-found responses as transient failures.
- Use exponential backoff with jitter for transient failures.
- Stop the run after repeated 429s or unexpected anti-automation responses.
- Record all failures with request fingerprints and error codes.

No concurrent or broad historical download should be enabled until Phase 1 and Phase 2 fixtures prove the endpoint behavior.

## Proposed CLI Commands

Do not implement yet.

Discovery and proof commands should start under `experimental`:

- `python -m albiz_collector.cli experimental qkb-document-discover --nipt <NIPT> --doc-type historical`
- `python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt <NIPT> --doc-type historical`
- `python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt <NIPT> --doc-type simple`
- `python -m albiz_collector.cli experimental qkb-document-fetch-one --nipt <NIPT> --doc-type rpp`

After endpoint and storage behavior are proven:

- `python -m albiz_collector.cli run qkb-documents --doc-type historical --limit <N>`
- `python -m albiz_collector.cli run qkb-documents --nipt <NIPT> --doc-type historical`
- `python -m albiz_collector.cli audit qkb-documents`
- `python -m albiz_collector.cli normalize qkb-documents`

Financial statement extraction should remain separate until document availability and PDF text quality are known:

- `python -m albiz_collector.cli experimental qkb-pdf-text --raw-fetch-id <ID>`
- `python -m albiz_collector.cli experimental qkb-financial-detect --raw-fetch-id <ID>`

Existing CLI command names should remain compatible.

## Proposed Tests

Endpoint discovery tests:

- Parse saved QKB search fixture and assert discovered document action types are exactly `rpp`, `simple`, and `historical`.
- Assert the parser finds calls to `fetchAndDisplayPDF` and `downloadButtonPress`.
- Assert no final PDF endpoint is returned when `document-handler.js` is absent.
- Add a saved `document-handler.js` fixture after live/manual verification and test exact endpoint extraction from that fixture.

Collector tests:

- Fake HTTP client test for one-NIPT fetch after endpoint verification.
- Assert request method, endpoint, headers, and payload match verified fixture evidence.
- Assert response bodies that are not valid PDFs are not saved as successful PDF documents.
- Assert PDF bytes are saved through `RawFetch`.
- Assert content hash is stable.

Idempotency tests:

- Same NIPT, document type, request fingerprint, and content hash should not duplicate metadata.
- Same NIPT and document type with a new content hash should create a new version.
- Cross-NIPT identical content hashes should be auditable, not silently merged.

CLI tests:

- Experimental command help tests before productionizing.
- Dry-run output tests that do not perform network calls.

PDF extraction tests:

- Local fixture PDF text extraction.
- Scanned/empty PDF handling.
- Extraction metadata capture, including page count and extraction warnings.

Financial detection tests:

- Text fixtures for positive and negative financial-statement detection.
- Avoid deriving normalized facts from low-confidence text until confidence rules are explicit.

## Implementation Phases

### Phase 1: Endpoint Discovery And One-NIPT Manual Proof

- Use browser developer tools on a single known NIPT from QKB search results.
- Click the historical extract viewer and download buttons.
- Capture `document-handler.js`.
- Capture network method, URL, headers, payload, status code, content type, and response shape.
- Save sanitized fixtures for `document-handler.js`, request metadata, and a small test PDF if legally safe.
- Prove whether replay requires a session.
- Do not add production collector behavior in this phase.

### Phase 2: Raw PDF Download And Storage

- Implement an experimental one-NIPT fetcher using verified endpoint evidence only.
- Save validated PDFs with `RawFetch`.
- Store request/response metadata in `RawFetch.extra_metadata`.
- Add unit tests with fake HTTP responses.
- Keep broad collection disabled.

### Phase 3: DB Metadata Persistence

- Add the approved document metadata table and Alembic migration.
- Persist document fetch attempts, statuses, request fingerprints, and raw fetch links.
- Implement idempotent resume behavior.
- Add audit command support.

### Phase 4: PDF Text Extraction

- Add a local-only text extraction module.
- Extract text from stored PDFs without new network activity.
- Store extraction metadata and warnings.
- Decide how to handle scanned PDFs and OCR separately.

### Phase 5: Financial-Statement Detection

- Detect likely financial statements from extracted text and document metadata.
- Use conservative rules: keywords, table/statement markers, year patterns, and QKB red-flag signals.
- Record confidence and reasons.
- Do not normalize financial facts from uncertain documents.

### Phase 6: Normalized Financial Facts

- Define normalized tables for financial statement facts after detection quality is known.
- Capture source document references, page/text spans where possible, fiscal year, units, and confidence.
- Add validation tests for balances, totals, and expected accounting relationships.

### Phase 7: Integration With Research Dataset / Features

- Join document-derived facts to existing QKB and procurement features by NIPT.
- Materialize research-ready features only from trusted normalized facts.
- Add profile/audit outputs for coverage, missingness, and confidence.

## Risks And Failure Modes

- The PDF endpoint may be in external `document-handler.js`, not in saved HTML.
- QKB may require browser cookies, WordPress state, or transient tokens.
- The frontend may return HTML or JSON errors instead of PDFs.
- `bilanciRedFlagText` may indicate financial-statement status without exposing the document through the same modal.
- PDFs may be scanned images requiring OCR.
- Historical extracts may be large, slow, or rate-limited.
- Different businesses may return identical placeholder PDFs.
- The same NIPT may return changing PDF content over time.
- Broad collection could unintentionally stress the public service if rate limits are not conservative.
- Encoding issues in saved HTML can affect exact label comparisons; tests should prefer structural selectors and `data-doc` values.

## Manual Verification Checklist

Before implementing production collection:

- Open QKB search for one known NIPT already present in collected search results.
- Confirm the search result modal shows `rpp`, `simple`, and `historical` document actions.
- Save the current `document-handler.js` as a fixture.
- Use browser network tools to click historical extract viewer.
- Record method, full URL, query/body fields, headers, status, content type, and response size.
- Repeat for historical extract download.
- Repeat for simple extract and RPP.
- Confirm whether the request succeeds in a fresh session.
- Confirm whether the request succeeds without prior modal red-flag request.
- Confirm how missing documents are represented.
- Confirm whether any financial statement document endpoint exists.
- Save sanitized request/response metadata fixtures.
- Verify downloaded bytes are valid PDFs and hash them.
- Only then implement the experimental one-NIPT fetcher.

## Intentional Non-Changes

- No production collector behavior changed.
- No scraper behavior changed.
- No parser behavior changed.
- No normalization or materialization behavior changed.
- No database models changed.
- No Alembic migrations created.
- No CLI command names changed.
- No live scraping was performed for this design.
- No real `.env` was created.
