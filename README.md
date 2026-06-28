# Albiz Collector

Albiz Collector is a Python data collection and materialization pipeline for a university thesis project on Albanian business dynamics. It collects public procurement and business-registry data, preserves raw source artifacts, converts them into normalized relational tables, and builds company-level feature tables for later statistical or machine-learning analysis.

## Current Thesis Scope

The implemented thesis workflow covers:

- APP public procurement export collection.
- QKB subject-search collection by date range, legal form, and exact NIPT.
- Targeted QKB lookup for known NIPT values.
- OpenCorporates HTML-derived financial enrichment for selected companies.
- Raw artifact storage, structured snapshots, normalized tables, feature tables, profiling, audits, and smoke checks.

The active thesis scope does not include a QKB Universe collector, batch QKB document extraction, historical extract PDF parsing, or financial-statement PDF parsing. Any remaining documents about those ideas should be treated as archived research notes, not as implemented pipeline documentation.

## High-Level Pipeline

```text
public source
  -> raw_fetches metadata + data/raw artifacts
  -> structured_records snapshots
  -> normalized_app_export_rows / normalized_qkb_search_rows
  -> app_company_features / qkb_company_features / joined_company_features
  -> profiling and audit outputs
```

OpenCorporates enrichment writes separate profile and financial-year tables:

- `opencorporates_company_profiles`
- `opencorporates_financial_years`

## Main Data Sources

- **APP**: Albanian Public Procurement Agency export page and yearly CSV exports.
- **QKB**: National Business Center subject-search page for registry identity and status data.
- **OpenCorporates**: Public company profile pages used as bounded, secondary financial enrichment.

## Documentation

- Practical setup and command reference: [PROJECT_SETUP_AND_COMMANDS.md](PROJECT_SETUP_AND_COMMANDS.md)
- Thesis-oriented technical source document: [THESIS_TECHNICAL_DOCUMENTATION.md](THESIS_TECHNICAL_DOCUMENTATION.md)
- Dataset documentation: [DATASET_DOCUMENTATION_DRAFT.md](DATASET_DOCUMENTATION_DRAFT.md)
- Short runnable examples: [run_examples.txt](run_examples.txt)
