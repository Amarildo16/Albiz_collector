# Full Audit Report

## Current Scope

This audit report describes the implemented repository scope after documentation cleanup. It is not a live verification log.

Supported thesis workflow:

- APP procurement export collection.
- QKB subject search collection.
- Targeted QKB lookup by NIPT.
- OpenCorporates financial enrichment.
- Normalization, feature materialization, profiling, audits, smoke checks, and scheduler.

Out of scope for the thesis implementation:

- QKB Universe collection.
- Batch QKB document extraction.
- QKB historical extract parsing.
- QKB PDF text extraction.
- QKB financial document extraction.

## Repository Structure Reviewed

- `src/albiz_collector/cli.py`
- `src/albiz_collector/config.py`
- `src/albiz_collector/models.py`
- `src/albiz_collector/sources/`
- `src/albiz_collector/normalization/`
- `src/albiz_collector/features/`
- `src/albiz_collector/profiling/`
- `src/albiz_collector/audit/`
- `src/albiz_collector/smoke/`
- `pyproject.toml`
- `.env.example`
- `alembic/versions/`

## Implemented Command Surface

Production commands:

- `python -m albiz_collector.cli init-db`
- `python -m albiz_collector.cli run app-exports`
- `python -m albiz_collector.cli run qkb-search`
- `python -m albiz_collector.cli run qkb-search-by-nipt`
- `python -m albiz_collector.cli run opencorporates-financials`
- `python -m albiz_collector.cli normalize app-exports`
- `python -m albiz_collector.cli normalize qkb-search`
- `python -m albiz_collector.cli normalize all`
- `python -m albiz_collector.cli features app`
- `python -m albiz_collector.cli features qkb`
- `python -m albiz_collector.cli features joined`
- `python -m albiz_collector.cli features all`
- `python -m albiz_collector.cli profile normalized`
- `python -m albiz_collector.cli profile features`
- `python -m albiz_collector.cli profile all`
- `python -m albiz_collector.cli profile qkb-legal-forms`
- `python -m albiz_collector.cli audit raw-fetches`
- `python -m albiz_collector.cli audit qkb-search-runs`
- `python -m albiz_collector.cli smoke app`
- `python -m albiz_collector.cli smoke qkb-search`
- `python -m albiz_collector.cli smoke all`
- `python -m albiz_collector.cli scheduler`

Experimental commands:

- `python -m albiz_collector.cli experimental qkb-notices`
- `python -m albiz_collector.cli experimental qkb-document-fetch-one`
- `python -m albiz_collector.cli experimental qkb-legal-form-chunk-probe`
- `python -m albiz_collector.cli experimental qkb-secondary-chunk-probe`
- `python -m albiz_collector.cli experimental opencorporates-financial-discovery`

## Data Pipeline Assessment

The active pipeline is internally consistent:

1. Collectors persist raw artifacts and structured snapshots.
2. Normalizers materialize APP and QKB normalized rows.
3. Feature commands aggregate company-level APP, QKB, and exact joined features.
4. Profiling reports readiness, sparsity, and join coverage.
5. Audits inspect raw artifact integrity and QKB run states.

The design is appropriate for a thesis dataset because it keeps raw provenance, avoids fuzzy joins, and makes derived tables rerunnable.

## Data Quality Controls

Implemented controls:

- Raw artifact SHA-256 hashes.
- Raw-fetch corruption flags and reasons.
- Raw-fetch integrity audit.
- Normalization skip behavior for quarantined raw artifacts.
- QKB search run tracking for resumable date-range collection.
- QKB legal-form profiling.
- Normalized and feature missingness profiling.
- Exact APP/QKB join coverage profiling.
- Live smoke checks for APP and QKB search contracts.

## Main Risks

- QKB search results can be source-capped, especially for dense date windows.
- QKB collection is not a full company-universe crawl.
- APP winner NIPT extraction is conservative and excludes ambiguous identifier values.
- OpenCorporates enrichment is secondary and may be sparse or unavailable for many companies.
- Public source pages can change HTML structure or response shape.
- Experimental commands should not be mixed into the thesis production workflow.

## Documentation Status

The main documentation now separates:

- concise project overview in `README.md`;
- practical command reference in `PROJECT_SETUP_AND_COMMANDS.md`;
- thesis source document in `THESIS_TECHNICAL_DOCUMENTATION.md`;
- dataset documentation in `DATASET_DOCUMENTATION_DRAFT.md`;
- short command examples in `run_examples.txt`;
- archived research notes for QKB Universe / historical extract ideas.
