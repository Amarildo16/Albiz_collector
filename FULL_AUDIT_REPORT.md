# Full Audit Report

## 1. Executive Summary
- This project is a Python scraping and data-materialization pipeline for Albanian procurement data from APP and business-registry data from QKB, with raw artifact retention, SQLAlchemy persistence, normalization, feature materialization, profiling, and research-semantics layers.
- Current health status: improved. The supported production collectors remain `app_exports` and `qkb_search`. `qkb_search` is now intentionally HTTP-only, date-range searches are chunked into inclusive one-day requests, and unfinished daily runs can resume from DB-backed saved progress. `qkb_notices_experimental` remains intentionally outside the supported production workflow.
- Production readiness: conditionally usable with fixes. This pass added DB-backed resumable qkb-search run tracking, restart support, run-state inspection, and migration-backed schema support for the new progress table.
- Biggest risks:
  - Historical raw-fetch provenance is still damaged for the already-quarantined rows in the local DB.
  - `qkb_search` is still coupled to the current inline JavaScript `response` contract.
  - The MySQL integration CI job exists, but is still optional/manual rather than a required PR gate.
- Biggest strengths:
  - Supported collectors are now backed by both fast unit coverage and a real MySQL integration path.
  - QKB date-range runs now persist progress day by day and can resume deterministically after interruption or handled failure.
  - Live source-contract smoke checks now exist for APP and QKB search and were verified successfully outside the sandbox with stale proxy vars unset.
  - Scheduler lookback windows now use `Europe/Tirane` explicitly and are tested.
  - The repo now has a practical runbook for migrations, maintenance, smoke checks, and the supported production flow.

## 2. Project Understanding
- Architecture summary:
  - `src/albiz_collector/config.py` loads env-driven runtime settings and stable raw-storage roots.
  - `src/albiz_collector/db.py` and `src/albiz_collector/models.py` define the SQLAlchemy engine, session factory, schema, and persisted qkb-search run-state table.
  - `src/albiz_collector/sources/` contains:
    - `app_exports.py`: APP export-page discovery and yearly CSV download.
    - `qkb_search.py`: QKB subject search via HTTP only, with inclusive one-day chunking, persisted resumable run-state, and inline-response extraction.
    - `qkb_notices_experimental.py`: exploratory notices capture only, not part of the supported production workflow.
    - `base.py`: shared raw persistence and structured snapshot upsert logic.
  - `src/albiz_collector/normalization/` materializes source-specific normalized tables.
  - `src/albiz_collector/features/` builds company-level feature tables.
  - `src/albiz_collector/profiling/` profiles normalized and feature tables.
  - `src/albiz_collector/semantics/` defines research-safe field and join semantics.
  - `src/albiz_collector/audit/` inventories raw-fetch integrity, can mark detected rows as corrupted, and can list persisted qkb-search run-state rows.
  - `src/albiz_collector/smoke/` now runs opt-in live source-contract checks for APP and QKB search.
  - `src/albiz_collector/utils/raw_fetches.py` centralizes corruption handling and exclusion filters.
  - `src/albiz_collector/scheduler.py` now computes rolling QKB search windows in `Europe/Tirane`.
  - `alembic/` provides versioned schema migrations against the project `DATABASE_URL`.
  - `.github/workflows/ci.yml` runs the fast unit suite by default and now supports an optional manual MySQL integration job.
- Main supported flows:
  - APP:
    - GET export index page.
    - Save raw index HTML.
    - Download yearly CSV export(s).
    - Save raw CSV artifact(s).
    - Upsert one `structured_records` snapshot per year.
    - Normalize CSV rows into `normalized_app_export_rows`.
    - Aggregate `app_company_features`.
  - QKB search:
    - HTTP mode only: GET the search page to establish session state, then POST the form-urlencoded payload back to the same endpoint.
    - Exact `nipt` searches remain single-request lookups.
    - Date-range searches without `nipt` are executed as inclusive one-day searches from `data_nga` through `data_ne`.
    - Each date-range run persists a `qkb_search_runs` row in the database.
    - `current_date` tracks the next unfinished day and is committed only after a successful day completes.
    - The same unfinished date-range run resumes from saved `current_date`; `--restart` forces a fresh run and interrupts the saved unfinished run for that range.
    - Days returning exactly `50` rows are surfaced as potentially truncated in the collector summary.
    - Parse the inline JavaScript `response` payload into a structured snapshot.
    - Normalize rows into `normalized_qkb_search_rows`.
    - Aggregate `qkb_company_features`.
  - Raw-fetch integrity / quarantine:
    - Read each `raw_fetches.storage_path`.
    - Resolve legacy relative paths backward-compatibly.
    - Hash file content and compare it to `raw_fetches.content_hash`.
    - Optionally mark mismatched or missing rows as corrupted using `is_corrupted` plus `corruption_reason`.
    - Downstream normalization, feature materialization, and normalized-data profiling ignore corrupted rows.
  - Source-contract smoke checks:
    - APP smoke check verifies the export index is reachable, export years are still parseable, and the expected download pattern hint is still present.
    - QKB search smoke check verifies the search page is reachable and still exposes the expected form and selectors used by the collector.
- Commands:
  - `python -m albiz_collector.cli run app-exports`
  - `python -m albiz_collector.cli run qkb-search --...`
  - `python -m albiz_collector.cli run qkb-search --data-nga YYYY-MM-DD --data-ne YYYY-MM-DD --restart`
  - `python -m albiz_collector.cli normalize all`
  - `python -m albiz_collector.cli features all`
  - `python -m albiz_collector.cli profile all`
  - `python -m albiz_collector.cli audit raw-fetches`
  - `python -m albiz_collector.cli audit qkb-search-runs`
  - `python -m albiz_collector.cli smoke app`
  - `python -m albiz_collector.cli smoke qkb-search`
  - `python -m albiz_collector.cli smoke all`
  - `python -m albiz_collector.cli scheduler`
  - `python -m albiz_collector.cli experimental qkb-notices`
  - `alembic upgrade head`
  - `alembic stamp head`
  - `alembic revision --autogenerate -m "..."`
  - `python -m unittest discover -s tests/integration -p "*_integration.py" -v`
- External dependencies:
  - APP:
    - `https://www.app.gov.al/export-public-calls/`
    - `https://www.app.gov.al/GetData/ExportDocument?year=YYYY`
  - QKB search:
    - `https://format.qkb.gov.al/kerko-per-subjekt/`
- Runtime services:
  - MySQL via `mysql+pymysql://root@localhost/albiz_collector` by default.
  - Playwright Chromium for browser-assisted experimental notices flows.
  - Alembic for schema migrations.

## 3. What I Verified
- Installation:
  - The usable runtime is the repo `.venv` with Python `3.12.9`.
  - In this shell, bare `python` resolves to `C:\Python314\python.exe`, so verification used `.venv\Scripts\python.exe`.
  - `pip install -r requirements.txt` still could not be cleanly verified in this sandbox because pip failed during temp-directory setup, not dependency resolution.
- Runtime / CLI:
  - `.venv\Scripts\python.exe -m albiz_collector.cli smoke --help` worked.
  - `.venv\Scripts\python.exe -m albiz_collector.cli run --help` still only lists supported production collectors.
  - `.venv\Scripts\python.exe -m albiz_collector.cli run qkb-search --help` worked and now exposes `--restart` while no longer exposing a Playwright flag.
  - `.venv\Scripts\python.exe -m albiz_collector.cli audit qkb-search-runs --help` worked.
  - `.venv\Scripts\python.exe -m albiz_collector.cli experimental qkb-notices --help` still exposes the experimental notices path separately.
- Unit tests:
  - `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
  - Result: `61` passed, `0` failed.
  - Newly verified areas:
    - HTTP-only qkb-search collector behavior
    - inclusive one-day date-range chunking
    - capped `50`-row day reporting
    - qkb-search resumable run creation, resume, restart, and completed-run behavior
    - qkb-search structured-snapshot dedup across reruns
    - smoke-check contract evaluation
    - scheduler timezone semantics
    - scheduler collector window wiring
- MySQL integration tests:
  - `.venv\Scripts\python.exe -m unittest discover -s tests\integration -p "*_integration.py" -v`
  - Environment: `RUN_MYSQL_INTEGRATION_TESTS=1`
  - Result: `3` passed, `0` failed.
  - Verified against a real MySQL server:
    - `alembic upgrade head` on a disposable DB
    - `init_db` then `alembic stamp head` adoption path
    - core row persistence
    - `materialize_qkb_search()` against real MySQL
- Live source-contract smoke checks:
  - Inside the sandbox, `.venv\Scripts\python.exe -m albiz_collector.cli smoke all` failed clearly because dead proxy env vars pointed to a refused local proxy. This was an expected environment failure mode, not a contract failure.
  - Outside the sandbox with proxy vars unset, `.venv\Scripts\python.exe -m albiz_collector.cli smoke all` passed:
    - APP: `200`, `17` years parsed, download hint present
    - QKB search: `200`, one form present, expected selectors present
- Scheduler behavior:
  - The new unit tests verified that Tirane-local date semantics are used even when the reference time would differ in UTC / host-local terms.
- CI:
  - The GitHub Actions workflow was updated and inspected locally.
  - Default path:
    - unit tests on Python `3.11` and `3.12`
  - Optional path:
    - manual `workflow_dispatch` MySQL integration job with a MySQL service container
- What passed:
  - fast unit suite
  - opt-in MySQL integration suite
  - live smoke checks for APP and QKB search outside the sandbox
  - scheduler timezone logic tests
- What failed:
  - `pip install -r requirements.txt` in this sandbox due temp-dir permission issues
  - live smoke checks inside the sandbox when dead proxy env vars were present
- What could not be fully verified:
  - GitHub-hosted execution of the optional MySQL integration job
  - PostgreSQL compatibility, despite `psycopg[binary]` still being present as a dependency

## 4. File/Module Review
- Root docs and config:
  - `README.md` now documents the fast unit suite, opt-in MySQL integration suite, smoke checks, and the runbook link.
  - `.env.example` now includes the supported QKB scheduler enable/lookback settings.
- CI:
  - `.github/workflows/ci.yml` now has:
    - fast default unit job on Python `3.11` / `3.12`
    - optional manual MySQL integration job with a service container
  - Quality: appropriate for the repo’s current maturity.
- `docs/deployment_and_migration_runbook.md`:
  - Purpose: production-safe operational guidance.
  - Quality: practical and aligned with the actual repo behavior.
  - Scope covered:
    - fresh DB setup
    - existing DB adoption via `alembic stamp head`
    - migration expectations
    - backup / rollback guidance
    - maintenance commands
    - smoke checks
    - MySQL integration tests
    - explicit separation of supported vs experimental flows
- `src/albiz_collector/smoke/`:
  - Purpose: opt-in live source-contract checks for supported collectors only.
  - Quality: intentionally small and low-risk.
  - Strength: does not mutate DB state and fails clearly when the contract is missing.
- `src/albiz_collector/sources/qkb_search.py`:
  - Purpose: supported QKB business-registry collector.
  - Quality: improved. The collector is now HTTP-only, avoids the previous split execution surface, emits deterministic one-day windows for non-NIPT date ranges, and persists resumable run-state safely after each successful day.
  - Remaining risk: parsing still depends on the live page keeping the inline `response` contract, and one-day searches that hit the `50`-row cap still require operator follow-up rather than automatic deeper splitting.
- `src/albiz_collector/models.py`:
  - Purpose: schema definition for persisted raw fetches, structured snapshots, normalized/materialized tables, and now qkb-search resumable run progress.
  - Quality: better aligned with production operation now that resumable daily run-state is modeled explicitly instead of being implicit in logs or the filesystem.
- `src/albiz_collector/audit/`:
  - Purpose: operational inspection for raw-fetch integrity and qkb-search run progress.
  - Quality: more useful now that operators can inspect saved qkb-search runs directly without querying the DB manually.
- `src/albiz_collector/scheduler.py`:
  - Purpose: recurring APP and QKB search execution.
  - Improvement: rolling QKB search windows now use `Europe/Tirane` explicitly.
  - Quality: the change is small, deterministic, and covered by unit tests.
- `tests/integration/`:
  - Purpose: opt-in real-MySQL validation.
  - Quality: good first integration layer.
  - Coverage:
    - migration path
    - bootstrap/stamp adoption path
    - persistence
    - normalization on MySQL
- `tests/scheduler/`:
  - Purpose: scheduler timezone and window behavior.
  - Quality: focused and useful.
- `tests/smoke/`:
  - Purpose: smoke-check contract evaluation logic without live network dependency.
  - Quality: targeted and stable.
- `tests/sources/`:
  - Purpose: qkb-search collector behavior under deterministic fake HTTP responses.
  - Quality: focused and high-value.
  - Coverage:
    - no Playwright CLI surface
    - inclusive day-by-day iteration
    - exact NIPT single-request behavior
    - resumable run creation and restart behavior
    - progress persistence after successful days only
    - completed runs not being resumed again
    - `50`-row truncation reporting
    - structured-snapshot dedup across reruns
- Supported collectors:
  - `app_exports.py` and `qkb_search.py` remain the supported production collectors.
  - `qkb_notices_experimental.py` remains explicitly outside the supported production workflow and was not changed functionally in this pass.

## 5. Confirmed Issues
| Title | Severity | Confidence | Affected Files | Explanation | Evidence | Suggested Fix |
| --- | --- | --- | --- | --- | --- | --- |
| Historical raw-fetch provenance was already damaged before the storage fix | high | confirmed | `src/albiz_collector/sources/base.py`, `src/albiz_collector/utils/storage.py`, `src/albiz_collector/audit/raw_fetches.py`, `src/albiz_collector/models.py` | Earlier filename reuse allowed on-disk overwrites while DB hashes stayed unchanged. Future writes are fixed, but historical rows remain damaged. | The configured local DB still contains already-quarantined rows from prior corruption. | Keep the quarantine system and decide on long-term remediation or permanent exclusion. |
| `qkb_notices_experimental` is not a real notices-ingestion pipeline | high | confirmed | `src/albiz_collector/sources/qkb_notices_experimental.py`, `src/albiz_collector/config.py` | It still does not satisfy the live notices search contract and should not be treated as production ingestion. | Earlier live verification yielded category snapshots, not actual notices. | Keep it experimental unless there is an explicit redesign decision. |
| Experimental notices date selector config remains dead code | medium | confirmed | `src/albiz_collector/config.py`, `src/albiz_collector/sources/qkb_notices_experimental.py` | `QKB_NOTICES_DATE_FROM_SELECTOR` and `QKB_NOTICES_DATE_TO_SELECTOR` are still defined but unused. | No usage remains in the code. | Remove them or implement them only if the experimental collector is ever redesigned. |
| Feature tables still require an explicit rebuild after quarantine if you want derived tables refreshed | low | confirmed | `src/albiz_collector/features/materialize.py`, `src/albiz_collector/profiling/report.py`, `README.md`, `docs/deployment_and_migration_runbook.md` | Quarantine affects source-row eligibility, but already-materialized feature tables are not rebuilt automatically by the audit command. | This remains an intentional explicit maintenance step. | Keep the explicit behavior and follow the documented rebuild flow. |

## 6. Likely Issues / Risks
| Title | Severity | Confidence | Affected Files | Explanation | Evidence | Suggested Fix |
| --- | --- | --- | --- | --- | --- | --- |
| QKB search parsing is coupled to the inline `response` JavaScript contract | medium | likely | `src/albiz_collector/sources/qkb_search.py` | The collector works now, but it assumes the page still exposes a parsable inline `response` variable. | The parser is regex-driven on current page markup. | Keep using the new smoke checks and add deeper live contract canaries if this path becomes business-critical. |
| APP export download is coupled to a configured URL pattern | medium | likely | `src/albiz_collector/config.py`, `src/albiz_collector/sources/app_exports.py` | The index page is parsed for years, but downloads still use the configured `GetData/ExportDocument?year={year}` pattern. | The collector formats URLs from config rather than using discovered hrefs. | Prefer discovered download hrefs when available. |
| QKB notices source URLs remain split across domains | medium | likely | `src/albiz_collector/config.py`, `data/raw/qkb_notices/.../shpallje-index.html` | The public index points to `qkb.gov.al/index.php/...`, while the experimental collector is configured for `format.qkb.gov.al/...`. | Earlier live snapshots showed the split-domain contract. | Only address this if the experimental notices collector is promoted out of its current de-scoped state. |
| QKB feature counts are observation counts, not event counts | low | likely | `src/albiz_collector/features/materialize.py` | `source_row_count` reflects normalized search observations, including overlapping windows. | Materialization groups all normalized QKB rows per business NIPT. | Keep the field, but continue documenting it as provenance rather than event-count truth. |

## 7. Test Coverage Assessment
- Current fast unit coverage now includes:
  - parser tests
  - DB/bootstrap tests
  - quarantine/integrity tests
  - normalization tests
  - feature/profiling tests
  - semantics tests
  - HTTP helper tests
  - storage-path tests
  - scheduler timezone tests
  - smoke-check evaluation tests
  - qkb-search source-collector behavior tests, including resumable run-state
- Current opt-in integration coverage now includes:
  - Alembic migration path on MySQL
  - `init_db` plus `alembic stamp head` adoption path on MySQL
  - core row persistence on MySQL
  - one normalization flow on MySQL
- Current automated totals verified locally:
  - unit suite: `61/61`
  - MySQL integration suite: `3/3`
- Remaining gaps:
  - no hosted CI proof yet for the MySQL integration job
  - no scheduler integration/end-to-end tests
  - no deeper live smoke coverage beyond page contract essentials
  - no PostgreSQL integration coverage

## 8. Security Review
- Findings:
  - No obvious shell-injection, unsafe deserialization, or arbitrary code execution patterns were found.
  - HTTPS is used for supported live source requests.
  - No hardcoded secrets were found in tracked source.
  - Proxy-related environment-variable behavior is documented and now demonstrated clearly by the smoke-check path.
  - Raw artifacts still live on local disk without an access-control abstraction.
- Risk level:
  - Moderate for a prototype / early production-hardening stage.
- Recommendations:
  - Keep the proxy documentation and smoke-check workflow.
  - Add structured logging with run IDs when operational complexity grows.
  - Continue using backups as the primary migration rollback safety net.

## 9. Performance / Reliability Review
- Findings:
  - Reliability improved further because:
    - supported collectors now have live smoke checks
    - the supported MySQL runtime path is validated separately from SQLite-based unit tests
    - scheduler date windows are deterministic in `Europe/Tirane`
  - The system still does full-table rebuilds for features and full-snapshot materialization for normalization.
  - `qkb_notices_experimental` remains intentionally outside the supported reliability story.
- Bottlenecks:
  - full feature rebuilds on every run
  - no incremental materialization strategy
  - still no automated deeper live drift monitoring beyond manual smoke checks
- Recommendations:
  - Keep the current simple rebuild model for now.
  - Use the new smoke checks intentionally before production changes and after suspected upstream site drift.
  - Consider promoting the optional MySQL integration CI job into a stronger gate once the team is comfortable with the runtime cost.

## 10. Maintainability Review
- Docs:
  - README and the new runbook are now materially stronger.
  - The supported production flow, maintenance path, integration tests, and smoke checks are documented clearly.
- Developer onboarding:
  - Better than before: a new developer now gets:
    - Alembic
    - a fast unit suite
    - an opt-in MySQL integration suite
    - smoke checks
    - a deployment/migration runbook
- Code clarity:
  - The new changes were small and focused.
  - No unnecessary data-model refactor was introduced in this pass.
- Remaining maintainability gap:
  - the MySQL integration job is still optional/manual, not a default required PR gate

## 11. Production Readiness Verdict
- Conditionally usable with fixes

Explain why:
- The supported collectors are now better hardened operationally.
- The repo has a real MySQL integration test path, a live smoke-check path, deterministic scheduler timezone behavior, and a practical runbook.
- The repo has a real MySQL integration test path, a live smoke-check path, deterministic scheduler timezone behavior, DB-backed resumable qkb-search runs, and a practical runbook.
- It is still not fully production-ready because:
  - historical corrupted raw rows remain in the local DB
  - QKB search still depends on a brittle live-site contract
  - live smoke checks are still manual rather than continuously enforced
  - the integration CI job is not yet a default required gate

## 12. Prioritized Action Plan
- Priority 0
  - Keep quarantined raw rows excluded from downstream use and decide the long-term policy for the already-corrupted historical rows.
  - Keep `qkb_notices_experimental` de-scoped unless there is an explicit decision to redesign and support it.
- Priority 1
  - Decide whether the optional MySQL integration CI job should become a regular required deployment or PR gate.
  - Decide how often smoke checks should be run operationally: release-only, pre-scheduler changes, or on a manual incident checklist.
  - Decide whether `qkb_search` days reported in `potentially_truncated_days` should stay as a reporting-only signal or trigger an operational alert / manual follow-up procedure.
  - Decide whether persisted qkb-search run rows should be retained indefinitely or pruned after a defined retention window.
  - Add a small migration/backup checklist to deployment operations outside the repo if this moves into shared team ownership.
- Priority 2
  - Prefer discovered APP download hrefs over the configured pattern.
  - Remove or implement the dead experimental notices selector settings.
  - Continue clarifying provenance-style feature counts in docs and table comments.
- Priority 3
  - Add incremental materialization strategies.
  - Add richer operational metrics and trend monitoring.
  - Consider object storage for raw artifacts.

## 13. Safe Fixes Applied
- Added an opt-in MySQL integration test harness with disposable databases and isolated raw-storage directories.
- Added MySQL integration tests covering:
  - `alembic upgrade head`
  - `init_db` plus `alembic stamp head`
  - core row persistence
  - `materialize_qkb_search()` on MySQL
- Added opt-in live source-contract smoke checks for APP and QKB search.
- Added unit tests for smoke-check contract evaluation.
- Fixed scheduler date-window logic to use `Europe/Tirane` explicitly.
- Added focused scheduler timezone tests.
- Added an operational runbook covering fresh DB setup, existing DB adoption, migrations, maintenance commands, smoke checks, integration tests, and experimental-flow separation.
- Updated README and `.env.example` to reflect the new supported operational and testing flows.
- Extended GitHub Actions with an optional manual MySQL integration job using a service container.
- Removed the qkb-search Playwright execution path and CLI surface, keeping the supported collector HTTP-only.
- Added deterministic qkb-search collector tests for:
  - inclusive one-day chunking of non-NIPT date ranges
  - exact NIPT single-request behavior
  - capped `50`-row day reporting
  - structured-snapshot dedup across reruns
- Updated qkb-search documentation to describe inclusive one-day chunking and `potentially_truncated_days` reporting.
- Added a migration-backed `qkb_search_runs` table for persisted resumable date-range progress.
- Added qkb-search resume/restart behavior with day-by-day committed progress and `--restart` support.
- Added an audit command to inspect saved qkb-search runs.
- Added qkb-search tests covering new-run creation, resume, restart, unrelated-range isolation, and completed-run behavior.

## 14. Remaining Open Questions
- Do you want the optional MySQL integration CI job to become a standard required gate on pull requests?
- Do you want the smoke checks to remain manual-only, or should they be added to a release checklist or a scheduled operational workflow?
- Do you want `qkb_search` days that hit the `50`-row cap to remain reporting-only, or should they feed a stronger alert / manual review workflow?
- Do you want persisted `qkb_search_runs` rows retained indefinitely, or should the project add a cleanup/retention policy?
- Do you want stronger concurrency protection for overlapping same-range qkb-search invocations, or is the current resumable single-row state enough for now?
- Do you want any long-term remediation beyond quarantine for the already-corrupted historical raw-fetch rows?
- Is MySQL the intended long-term supported database, or should the project still standardize elsewhere later?
