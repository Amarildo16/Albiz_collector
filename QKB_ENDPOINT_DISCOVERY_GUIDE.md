# QKB Endpoint Discovery Guide

Date: 2026-04-24

This guide prepares Phase 1 discovery for QKB subject document PDFs. It is for manual evidence capture only. Do not add production collector behavior, broad scraping, migrations, or guessed endpoints from this guide.

## Evidence Rule

Treat an endpoint as confirmed only if it appears in a saved JavaScript fixture or captured browser Network evidence. The existing QKB search HTML fixture confirms document action types and frontend function calls, but it does not confirm the final PDF endpoint.

## Setup

Use one manually selected NIPT from already collected QKB search results. Keep the run small: one subject, one browser session, and one click per document action unless a retry is needed to understand a failure.

Before capture:

- Confirm no real `.env` is needed or created.
- Open browser developer tools before clicking document buttons.
- Enable Preserve log in the Network panel.
- Disable cache while developer tools are open.
- Filter by `fetch`, `xhr`, `document`, and `pdf` if the browser supports those filters.
- Be ready to sanitize cookies, session identifiers, IP addresses, user-specific headers, and any private local paths before saving fixtures.

## Capture `document-handler.js`

1. Open the QKB search page that shows the subject detail modal.
2. In the Network panel, reload the page with Preserve log enabled.
3. Find the request ending in `document-handler.js`.
4. Record:
   - Request method.
   - Full URL.
   - Response status.
   - Response content type.
   - Response size.
   - Response hash if available.
5. Save the response body as `tests/fixtures/qkb_documents/document-handler.js`.
6. Inspect the saved JavaScript for:
   - `fetchAndDisplayPDF`.
   - `downloadButtonPress`.
   - Any endpoint path or URL used for PDFs.
   - Request method.
   - Request body/query parameter names.
   - Required headers.
   - Error handling for missing documents.

Only endpoint values found in this saved JavaScript should be marked as JavaScript-confirmed.

## Capture Historical Extract Viewer Request

1. Clear the Network panel.
2. Open the subject detail modal for the selected NIPT.
3. Click the historical extract viewer button, not the download button.
4. Identify the request made by `fetchAndDisplayPDF`.
5. Save sanitized request metadata as `tests/fixtures/qkb_documents/historical-view-request.json`.
6. Record:
   - Document action: `historical` viewer.
   - Request method.
   - Full URL.
   - Query parameters.
   - Form/body payload, including exact field names.
   - Relevant replay headers.
   - Whether cookies are sent.
   - Whether the request succeeds in the same session only.
   - Response status.
   - Response content type.
   - Response size.
   - Whether the response body starts with `%PDF`.
   - Any redirect chain.
   - Any error body if the response is not a PDF.

Relevant replay headers usually include `Accept`, `Content-Type`, `Origin`, `Referer`, and user-agent-sensitive headers only if the server appears to require them. Do not preserve raw `Cookie` headers in fixtures.

## Capture Historical Extract Download Request

1. Clear the Network panel.
2. Open the subject detail modal for the same selected NIPT.
3. Click the historical extract download button.
4. Identify the request made by `downloadButtonPress`.
5. Save sanitized request metadata as `tests/fixtures/qkb_documents/historical-download-request.json`.
6. Record the same fields as the viewer request.
7. Additionally record:
   - `Content-Disposition` response header if present.
   - Browser-suggested filename if visible.
   - Whether the download request differs from the viewer request.

## Capture Simple Extract Request

1. Clear the Network panel.
2. Click the simple extract viewer button.
3. Save sanitized request metadata as `tests/fixtures/qkb_documents/simple-view-request.json`.
4. Record the same fields as the historical viewer request.
5. Note whether only the document type changes or whether the endpoint/payload shape also changes.

If the simple extract download request differs materially from the viewer request, add a separate sanitized fixture named `simple-download-request.json`.

## Capture RPP Request

1. Clear the Network panel.
2. Click the RPP viewer button.
3. Save sanitized request metadata as `tests/fixtures/qkb_documents/rpp-view-request.json`.
4. Record the same fields as the historical viewer request.
5. Note whether only the document type changes or whether the endpoint/payload shape also changes.

If the RPP download request differs materially from the viewer request, add a separate sanitized fixture named `rpp-download-request.json`.

## Check Cookies And Session Requirement

For each confirmed document request:

1. Copy the sanitized request details.
2. Replay the request in a fresh browser profile or HTTP client without cookies.
3. Replay the request after first loading the QKB search page but before opening the modal.
4. Replay the request after opening the modal and red-flag request.
5. Record which setup succeeds.

Do not store raw cookies or session tokens. If cookies are required, record only that a session is required and list cookie names if they are non-sensitive and useful.

## Check PDF Validity

For each successful response:

- Confirm status is expected, usually `200`.
- Confirm `Content-Type` is `application/pdf` or otherwise explain the server behavior.
- Save response size in bytes.
- Verify the first bytes are `%PDF`.
- Compute SHA-256 for the bytes.
- Save only metadata unless storing a tiny/sanitized PDF fixture is legally safe.

If the response is HTML, JSON, empty, or a redirect to an error page, it is not a confirmed PDF response.

## Missing-Document Behavior

Capture missing-document behavior only if it can be observed without broad probing.

Record:

- Which document type was missing.
- Whether the frontend still made a request.
- Request method and URL.
- Response status.
- Response content type.
- Response body shape, summarized and sanitized.
- Whether the response starts with `%PDF`.
- Whether the UI displayed an alert, spinner timeout, empty iframe, or downloaded placeholder.

Do not try many random NIPTs to force missing-document cases.

## Suggested Request Metadata Shape

Use this shape for sanitized request fixtures:

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

## Sanitization Rules

- Do not save real cookies, authorization headers, session IDs, browser profile paths, local usernames, or private notes.
- Replace sensitive values with `SANITIZED`.
- Keep endpoint paths, method, payload field names, document type values, status, content type, and response size intact.
- If a NIPT is already public and needed for reproducibility, mark it as public test data in the fixture notes.
- Do not save full PDFs unless the file is legally safe and intentionally tiny.

## Phase 1 Completion Criteria

Phase 1 is complete when the repository has sanitized fixtures proving:

- The current `document-handler.js` implementation.
- The historical viewer request.
- The historical download request.
- The simple extract request.
- The RPP request.
- Whether cookies/session state are required.
- Whether successful responses are valid PDFs.
- How missing documents are represented, if observed safely.

Only after those fixtures exist should code move from offline discovery helpers to an experimental one-NIPT fetcher.
