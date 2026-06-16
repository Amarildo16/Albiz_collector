# QKB Universe And Financials Plan

Date: 2026-06-16

Scope: technical feasibility analysis only. This report does not implement code, migrations, tests, or new collectors.

## Evidence Levels

- **Already implemented/proven:** Present in source code and covered by tests or existing project documentation.
- **Inferred but not proven:** Suggested by current forms, endpoints, or model shape, but not implemented or fully validated.
- **Unknown/manual inspection required:** Not established by current code or tests.

## 1. Current QKB Capabilities Already Implemented

### Already implemented/proven

The project has an HTTP QKB search collector in `src/albiz_collector/sources/qkb_search.py`.

Supported search modes:

- Search by NIPT through `python -m albiz_collector.cli run qkb-search --nipt ...`.
- Search by date range through `--data-nga` and `--data-ne`.
- Date-range collection without `--nipt` is chunked into one-day requests.
- Date-range collection without `--nipt` is resumable through `QkbSearchRun`.
- `--restart` is supported for date-range collection without `--nipt`.

The collector posts to the configured QKB search URL using form fields that include:

- `nipt`
- `dataNga`
- `dataNe`
- `formeLigjore`
- `qarku`
- `qyteti`
- `emriISubjektit`
- `emriTregtar`

The parser extracts the JavaScript `response` variable from the returned QKB page and stores the result as a `StructuredRecord` with:

- `source_name = "qkb_search"`
- `record_type = "qkb_search_snapshot"`
- `external_key = nipt|date_from|date_to`

The date-range collector tracks potentially truncated daily searches. QKB returns at most 50 records per search in current project assumptions/tests, and one-day searches returning exactly 50 rows are flagged as potentially truncated.

The CLI currently exposes:

- `run qkb-search`
- `normalize qkb-search`
- `features qkb`
- `features joined`
- `audit qkb-search-runs`
- `smoke qkb-search`
- `experimental qkb-document-fetch-one`
- `experimental qkb-notices`

QKB document fetching exists in `src/albiz_collector/sources/qkb_documents.py` as an experimental one-NIPT helper.

Supported document types are:

- `historical`
- `simple`
- `rpp`

The document client posts to:

`https://format.qkb.gov.al/wp-content/themes/twentytwentyfive-child/modules/search/national-registry/subject/search-for-subject-get-documents.php`

with form fields:

- `nipt`
- `docType`

Successful document responses are expected to be JSON objects containing a positive `status` and base64 PDF data. The client verifies that decoded bytes begin with `%PDF`.

Successful PDF results can be saved as `RawFetch` rows with:

- `source_name = "qkb_documents"`
- `fetch_kind` mapped by document type, for example `historical_extract_pdf`
- `content_type = "application/pdf"`
- document metadata in `extra_metadata`

### Proven by tests

Current tests prove these QKB behaviors:

- QKB search CLI exposes the expected arguments.
- Date ranges without NIPT are split into inclusive daily chunks.
- Single-day date ranges work.
- NIPT plus date range remains a single request and does not create resumable run state.
- Daily searches returning exactly 50 rows are marked as potentially truncated.
- Failed daily runs resume from the failed day rather than skipping it.
- `--restart` interrupts an unfinished run and starts a new one.
- Completed date-range runs are not resumed.
- QKB search parser extracts saved `response` payloads and rejects pages without the response variable.
- QKB search normalization persists normalized rows and is safe to rerun.
- Corrupted raw fetches are skipped during normalization.
- QKB document client posts the expected endpoint, payload, and headers for `historical`, `simple`, and `rpp`.
- Invalid document type `bilanci` is rejected.
- Successful document responses decode to verified PDF bytes.
- `status = 0` is handled as not found.
- Negative status is handled as server error.
- malformed JSON and non-PDF base64 are rejected.
- A successful historical PDF result can be saved as a `RawFetch`.
- The experimental document CLI help exposes one-NIPT options and does not expose a batch document collector.
- Saved QKB document action evidence shows `rpp`, `simple`, and `historical` document actions.

### Inferred but not proven

The search form includes fields such as legal form, city, county, and names. These may be usable for finer sub-chunking when a daily search hits the 50-row limit, but the current collector does not implement this and tests do not prove it.

### Unknown/manual inspection required

It is not proven that every QKB business can be collected losslessly with only one-day date chunks. High-volume days can still truncate at 50 results.

It is not proven that the QKB document endpoint exposes financial statements, balance sheets, CSV files, or Excel files.

## 2. What QKB Data We Can Currently Normalize

### Already implemented/proven

`src/albiz_collector/normalization/qkb_search.py` currently normalizes QKB search result rows into `normalized_qkb_search_rows`.

Normalized fields include:

- `search_nipt`
- `search_date_from`
- `search_date_to`
- `business_nipt`
- `business_name`
- `trade_name`
- `legal_form`
- `registration_date`
- `city`
- `ownership_text`
- `subject_status`
- `subject_type`
- `activity_text`
- `administrators_text`
- `has_red_flags`
- `source_payload`

The QKB company feature layer currently materializes company-level registry features from normalized QKB rows, including:

- `company_nipt`
- `source_row_count`
- `distinct_search_snapshot_count`
- `business_name`
- `trade_name`
- `legal_form`
- `subject_status`
- `registration_date`
- `registration_year`
- `city`
- `has_red_flags`
- `has_activity_text`
- `has_ownership_text`
- search window fields

### Inferred but not proven

The normalized fields are enough to build a first-pass QKB business universe keyed by `business_nipt`, but no dedicated `qkb_universe_businesses` table is currently implemented.

### Unknown/manual inspection required

The completeness and consistency of fields such as `activity_text`, `ownership_text`, `administrators_text`, and `has_red_flags` across all years/business types is not yet proven.

## 3. QKB Universe Collection Strategy

### Already implemented/proven

The existing QKB search collector can collect broad search results by date range when no NIPT is provided. It already chunks the range into one-day requests and stores resumable run state in `qkb_search_runs`.

The safest currently implemented broad collection path is:

1. Run QKB search over a date range without `--nipt`.
2. Let the collector split the range into daily requests.
3. Normalize `qkb_search` results.
4. Deduplicate businesses downstream by `business_nipt`.

The current run state can resume interrupted daily collection. Progress advances only after a daily chunk is successfully saved.

### Inferred but not proven

A future universe collector can reuse the current daily date-range search as its base collection primitive.

Because daily searches can still return exactly 50 rows, a production-grade universe collector should add secondary chunking when a day is potentially truncated. Possible secondary dimensions are visible in the search form and request payload:

- legal form
- city
- county
- subject name prefix
- status or type if supported by the form/backend

This is not implemented today and should be validated with a small manual sample before relying on it.

### Recommended chunking approach

Use daily chunks as the first level:

- `dataNga = day`
- `dataNe = day`

For any day returning fewer than 50 rows:

- treat the day as probably complete, subject to QKB behavior remaining stable.

For any day returning exactly 50 rows:

- mark it as potentially truncated.
- do not assume completeness.
- retry that day using validated secondary chunk dimensions.

Suggested validation order for secondary chunking:

1. Legal form, because SHPK filtering is a primary downstream need.
2. City or county, if legal-form chunks still hit 50.
3. Name prefix only if needed, because it is more complex and more likely to create edge cases.

### Resume strategy

The current `QkbSearchRun` model supports resumable daily ranges. A future universe collector should preserve the same properties:

- one persistent run row per logical date range and mode.
- current date tracked after each successful chunk.
- failed day retried on the next run.
- explicit restart required to discard unfinished progress.
- summary fields recording potentially truncated days.

For secondary chunking, future run state should also record:

- chunk dimension
- chunk value
- chunk status
- row count
- truncation flag
- raw fetch or structured record reference

### Duplicate avoidance

Current storage already helps avoid duplicate snapshots:

- `StructuredRecord` uses source, record type, and external key.
- normalized QKB rows are tied to structured records and ordinals.
- QKB company features group by business NIPT.

A future universe table should use:

- `business_nipt` as the unique business key when present.
- source snapshot references for provenance.
- deterministic conflict handling when the same NIPT appears in multiple searches.

Do not use business name as an identity key.

### Unknown/manual inspection required

It is unknown whether daily chunks plus legal form are sufficient for all high-volume dates. This must be tested on days that currently return exactly 50 rows.

## 4. SHPK Filtering Strategy

### Already implemented/proven

QKB search normalization preserves the source legal form in `legal_form`.

Fixture data shows normalized values such as:

- `SHPK`
- `Person Fizik`

The search form fixture includes a legal-form option corresponding to:

- `Shoqeri me pergjegjesi te kufizuar`

### Inferred but not proven

SHPK filtering should use the QKB `legal_form` field, not company name text.

The raw legal-form field is probably reliable enough for first-pass filtering because it comes directly from QKB structured search results, but variants should be normalized before use.

Recommended canonicalization:

- uppercase
- trim whitespace
- collapse repeated spaces
- remove punctuation such as `.`
- normalize accented Albanian characters to accentless forms
- map known variants to a canonical value such as `SHPK`

Expected variants to handle:

- `SHPK`
- `SH.P.K`
- `SH.P.K.`
- `Shoqeri me pergjegjesi te kufizuar`
- accented variants of the long Albanian form

### Unknown/manual inspection required

The full set of legal-form variants in live QKB results is not known. Before implementing a hard filter, inspect distinct `legal_form` values from normalized QKB rows.

## 5. Historical Extract And Financial Documents Strategy

### Already implemented/proven

The current document client can fetch one document for one NIPT for these document types:

- `historical`
- `simple`
- `rpp`

The historical document path is supported by:

- endpoint discovery documentation.
- fixture evidence showing a positive response with base64 PDF data.
- tests validating PDF magic bytes.
- a CLI command for one-NIPT experimental fetches.

The current code can save successful documents as raw PDF fetches.

### Inferred but not proven

The same endpoint pattern may support only the currently discovered document types. Current code intentionally restricts document types to `historical`, `simple`, and `rpp`.

The historical extract PDF may contain useful company history, but parsing its text or structured events is not implemented.

### Unknown/manual inspection required

Financial statement or balance sheet extraction is not proven.

Current tests explicitly reject `bilanci` as an invalid document type. No current code proves that a balance-sheet document type exists, and no current code proves CSV or Excel availability for financial statements.

Manual inspection is needed for a small SHPK sample:

1. Fetch `historical`, `simple`, and `rpp` documents for several known SHPK companies.
2. Inspect whether any PDF contains references to financial statements.
3. Inspect QKB pages and network requests for any separate financial document actions.
4. Determine whether files are PDFs, images, CSV, Excel, or another format.
5. Determine whether financial statements are downloadable by year.
6. Determine whether text extraction is enough or OCR is required.

Do not build a broad financial parser until this sample inspection proves the file types and source semantics.

## 6. Proposed Database Design For Next Phases

This section proposes future tables or normalized datasets only. No schema changes are implemented by this report.

### `qkb_universe_businesses`

Purpose: one row per known QKB business.

Suggested fields:

- `business_nipt`
- `business_name`
- `trade_name`
- `legal_form_raw`
- `legal_form_canonical`
- `subject_status`
- `subject_type`
- `registration_date`
- `registration_year`
- `city`
- `activity_text`
- `ownership_text`
- `administrators_text`
- `has_red_flags`
- `first_seen_at`
- `last_seen_at`
- `first_source_structured_record_id`
- `last_source_structured_record_id`
- `source_row_count`
- `source_snapshot_count`

Constraints:

- unique on `business_nipt` where present.
- deterministic update policy when later snapshots disagree.

### `qkb_business_documents`

Purpose: metadata and provenance for QKB document fetch attempts.

Suggested fields:

- `business_nipt`
- `document_type`
- `fetch_status`
- `backend_status`
- `raw_fetch_id`
- `endpoint`
- `request_payload_hash`
- `content_hash`
- `content_type`
- `verified_pdf_magic`
- `fetched_at`
- `error_reason`

Recommended uniqueness:

- one latest row per `business_nipt`, `document_type`, and content hash, or
- one attempt row per request plus a separate latest-success view.

### `qkb_historical_extracts`

Purpose: parsed or extracted content from historical extract PDFs.

Suggested fields:

- `business_nipt`
- `business_document_id`
- `raw_fetch_id`
- `extraction_method`
- `extraction_status`
- `text_content`
- `text_hash`
- `page_count`
- `requires_ocr`
- `parsed_event_count`
- `parsed_payload`
- `created_at`

Do not assume structured history events are available until PDF text extraction has been tested.

### `qkb_financial_statement_files`

Purpose: discovered financial document files, if such documents are proven to exist.

Suggested fields:

- `business_nipt`
- `source_document_id`
- `raw_fetch_id`
- `financial_document_type`
- `statement_year`
- `file_type`
- `content_type`
- `content_hash`
- `download_url`
- `fetch_status`
- `extraction_status`
- `requires_ocr`
- `manual_review_status`

The `file_type` field should remain descriptive until real samples prove whether files are PDF, image, Excel, CSV, or another format.

### `qkb_financial_statement_rows`

Purpose: normalized line items from financial statements, if parsable.

Suggested fields:

- `business_nipt`
- `financial_statement_file_id`
- `statement_year`
- `statement_type`
- `metric_name_raw`
- `metric_name_canonical`
- `amount`
- `currency`
- `unit`
- `source_page`
- `source_row`
- `parse_confidence`
- `extraction_method`

### Yearly financial features

If row-level financial parsing becomes reliable, create a separate deterministic feature table such as `qkb_company_financial_yearly_features`.

Suggested fields:

- `business_nipt`
- `statement_year`
- `revenue_amount`
- `asset_total_amount`
- `liability_total_amount`
- `equity_total_amount`
- `profit_loss_amount`
- `employee_count`
- `source_file_count`
- `has_financial_statement_file`
- `financial_parse_confidence`

Do not create target labels or risk labels in these tables.

## 7. Proposed CLI Phases

These are future command suggestions only.

The current CLI uses verbs such as `run`, `normalize`, `features`, `profile`, `audit`, `smoke`, and `experimental`. New commands should fit that style unless the project intentionally introduces a `collect` alias.

Suggested phases:

- `run qkb-universe --data-nga YYYY-MM-DD --data-ne YYYY-MM-DD`
- `normalize qkb-universe`
- `filter qkb-shpk` or `features qkb-shpk`
- `run qkb-documents --document-type historical --source qkb-shpk`
- `experimental inspect qkb-financial-documents --sample-size N`
- `parse qkb-financials`

Recommended rollout:

1. Keep broad QKB universe collection separate from document fetching.
2. Keep document discovery separate from document parsing.
3. Keep financial document inspection experimental until file types and source semantics are proven.
4. Keep batch document fetching opt-in and resumable.

## 8. Risks And Blockers

### Rate limits and operational pressure

QKB may throttle, block, or change behavior under sustained traffic. A broad universe collector should use conservative pacing, resumable runs, and clear stop/retry behavior.

### Search result truncation

The 50-result limit is the main completeness risk. Daily chunking reduces but does not eliminate this risk.

Days returning exactly 50 rows must be treated as incomplete until secondary chunking proves otherwise.

### Endpoint drift

The QKB search page relies on embedded JavaScript response data. The document endpoint is an implementation detail of the QKB website. Both can change without notice.

### Missing documents

Some businesses may not have all document types. The document client already handles `status = 0` as not found.

### PDF/image/CSV/Excel uncertainty

Historical/simple/RPP documents are currently proven as PDFs. Financial statements are not proven. They may be PDFs, scanned images, Excel files, CSV files, or not available through the discovered endpoint.

### OCR risk

If financial statements or historical extracts are scanned PDFs/images, reliable extraction may require OCR. OCR introduces accuracy, runtime, and review challenges.

### Legal and ethical limits

Broad collection should respect public-site terms, rate limits, and privacy/legal constraints. The project should avoid aggressive crawling and should retain provenance for public-source records.

### Runtime and storage

Full-universe collection plus document fetching may involve many HTTP requests and many PDF files. Storage paths, content hashes, retry state, and cleanup/audit tooling should be planned before broad execution.

### Semantic ambiguity

Fields such as `has_red_flags`, `activity_text`, and `ownership_text` are registry signals, not prediction labels. They should not be used or described as bankruptcy, fraud, or risk labels.

## 9. Recommended Next Implementation Step

The next coding step should be small and non-networked:

Add a tested QKB legal-form canonicalization helper and an SHPK filter preview over existing normalized QKB rows.

Why this step:

- It supports the SHPK business-universe goal directly.
- It does not require broad crawling.
- It can be tested with fixtures and distinct existing `legal_form` values.
- It reduces ambiguity before document collection begins.

Suggested acceptance criteria:

- `SHPK`, `SH.P.K`, `SH.P.K.`, and long Albanian legal-form variants all canonicalize to `SHPK`.
- unknown legal forms remain preserved as raw values and produce a deterministic canonical fallback.
- the preview reports counts by raw and canonical legal form.
- no QKB backfill or document fetching is triggered.

## Summary

### Already implemented/proven

- QKB search by NIPT.
- QKB search by date range.
- Daily chunking for no-NIPT date ranges.
- Resumable date-range search runs.
- Search result normalization into company registry fields.
- QKB company features and exact-NIPT joined features.
- Experimental one-NIPT fetching for `historical`, `simple`, and `rpp` PDFs.
- Raw PDF persistence for successful document fetches.

### Inferred but not proven

- Existing date-range search can be the base primitive for a broader QKB business universe.
- Secondary chunking by legal form/city/name may resolve the 50-row truncation risk.
- `legal_form` is the correct basis for SHPK filtering, provided variants are canonicalized.

### Unknown/manual inspection required

- Whether daily plus secondary chunks can collect the universe without truncation.
- Whether financial statement documents are exposed by QKB.
- Whether financial files are PDFs, images, CSV, Excel, or another format.
- Whether historical extract PDFs can be parsed reliably without OCR.
