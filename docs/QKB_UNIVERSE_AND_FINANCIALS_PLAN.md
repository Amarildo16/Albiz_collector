Archived research idea. Not part of the current thesis implementation.

# QKB Universe And Financials Plan

This file is retained as an archived research note only.

The current thesis implementation does not include:

- QKB Universe collection;
- batch QKB document extraction;
- QKB historical extract parsing;
- QKB PDF text extraction;
- QKB financial-document extraction.

Implemented QKB functionality is limited to:

- production QKB subject search through `run qkb-search`;
- production targeted NIPT lookup through `run qkb-search-by-nipt`;
- normalization into `normalized_qkb_search_rows`;
- QKB company feature materialization;
- exact APP/QKB joined feature materialization;
- profiling and audits for QKB search data.

OpenCorporates financial enrichment is implemented separately through:

```powershell
python -m albiz_collector.cli run opencorporates-financials
```

Any older design notes about full QKB universe discovery, QKB document batches, PDF parsing, or financial extraction from QKB documents should not be cited as implemented project functionality.
