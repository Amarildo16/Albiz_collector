# QKB Document Fixture Staging

This directory is reserved for sanitized Phase 1 endpoint-discovery evidence for QKB subject documents.

Do not store real cookies, session tokens, authorization headers, private browser profile paths, or broad scraped data here. Endpoint values should be treated as confirmed only when they come from a saved JavaScript fixture or captured browser Network evidence.

Current and expected files:

- `document-handler.js`: saved response body for the frontend document handler that defines `fetchAndDisplayPDF` and `downloadButtonPress`.
- `historical-view-request.json`: sanitized browser Network metadata for the historical extract viewer request. This fixture records the confirmed POST endpoint and base64 PDF response shape without storing the full PDF.
- `historical-download-request.json`: sanitized browser Network metadata for the historical extract download request.
- `simple-view-request.json`: sanitized browser Network metadata for the simple extract viewer request.
- `simple-download-request.json`: optional, only if simple download differs materially from simple view.
- `rpp-view-request.json`: sanitized browser Network metadata for the RPP viewer request.
- `rpp-download-request.json`: optional, only if RPP download differs materially from RPP view.
- `sample-response-metadata.json`: response-level metadata shared across proof captures, such as status, content type, size, PDF magic result, and SHA-256 hashes.
- `sample.pdf`: optional tiny or sanitized PDF fixture, only if legally safe to commit.

Suggested request metadata shape:

```json
{
  "capture_date": "2026-04-24",
  "evidence_source": "browser_network",
  "document_action": "historical_view",
  "document_type": "historical",
  "nipt_value": "SANITIZED_OR_PUBLIC_TEST_NIPT",
  "request": {
    "method": "POST_OR_GET",
    "url": "https://example.invalid/confirmed/path",
    "query_params": {},
    "body_kind": "form|json|none|unknown",
    "body": {},
    "headers_relevant_to_replay": {
      "Accept": "",
      "Content-Type": "",
      "Origin": "",
      "Referer": ""
    },
    "cookies_sent": "yes|no|unknown",
    "cookie_names_if_required": []
  },
  "response": {
    "status_code": 200,
    "content_type": "application/pdf",
    "content_length": 0,
    "starts_with_pdf_magic": true,
    "sha256": "",
    "content_disposition": "",
    "redirect_chain": []
  },
  "session_requirement": {
    "works_without_cookies": "yes|no|unknown",
    "requires_prior_search_page": "yes|no|unknown",
    "requires_modal_opened_first": "yes|no|unknown"
  },
  "notes": ""
}
```

Keep full URLs, endpoint paths, HTTP methods, payload field names, document type values, response status, response content type, and response size intact. Sanitize credentials and session state.
