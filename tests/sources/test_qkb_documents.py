from __future__ import annotations

import base64
import json
import re
import unittest
from unittest.mock import patch

from sqlalchemy import select
from typer.testing import CliRunner

from albiz_collector.cli import app
from albiz_collector.db import Base
from albiz_collector.models import RawFetch
from albiz_collector.sources.qkb_documents import (
    ALLOWED_QKB_DOCUMENT_TYPES,
    QKB_DOCUMENTS_ENDPOINT,
    QKB_DOCUMENT_REQUEST_HEADERS,
    QkbDocumentClient,
    QkbDocumentCollector,
    QkbDocumentResponseError,
    build_qkb_document_request_payload,
)
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PDF_BASE64 = base64.b64encode(PDF_BYTES).decode("ascii")


class _FakeHttpClient:
    def __init__(self, payload: dict[str, object] | str, *, content_type: str | None = None) -> None:
        self.payload = payload
        self.content_type = content_type or "text/html; charset=UTF-8"
        self.post_calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies=None,
    ) -> ResponsePayload:
        self.post_calls.append(
            {
                "url": url,
                "data": dict(data or {}),
                "headers": dict(headers or {}),
                "cookies": cookies,
            }
        )
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        content = text.encode("utf-8")
        return ResponsePayload(
            url=url,
            status_code=200,
            content_type=self.content_type,
            content=content,
            text=text,
            cookies=None,
        )


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


class QkbDocumentClientTests(unittest.TestCase):
    def test_build_request_payload_for_allowed_document_types(self) -> None:
        for doc_type in ALLOWED_QKB_DOCUMENT_TYPES:
            with self.subTest(doc_type=doc_type):
                payload = build_qkb_document_request_payload(nipt=" m12345678a ", doc_type=doc_type)

                self.assertEqual(payload, {"nipt": "M12345678A", "docType": doc_type})

    def test_client_posts_confirmed_endpoint_payload_and_headers_for_each_doc_type(self) -> None:
        for doc_type in ALLOWED_QKB_DOCUMENT_TYPES:
            with self.subTest(doc_type=doc_type):
                http = _FakeHttpClient({"status": 1, "data": PDF_BASE64})

                result = QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type=doc_type)

                self.assertEqual(len(http.post_calls), 1)
                self.assertEqual(http.post_calls[0]["url"], QKB_DOCUMENTS_ENDPOINT)
                self.assertEqual(http.post_calls[0]["data"], {"nipt": "M12345678A", "docType": doc_type})
                expected_headers = {
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://format.qkb.gov.al",
                    "Referer": "https://format.qkb.gov.al/kerko-per-subjekt/",
                }
                self.assertEqual(QKB_DOCUMENT_REQUEST_HEADERS, expected_headers)
                self.assertEqual(http.post_calls[0]["headers"], expected_headers)
                self.assertIsNone(http.post_calls[0]["cookies"])
                self.assertEqual(result.backend_state, "success")

    def test_invalid_document_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_qkb_document_request_payload(nipt="M12345678A", doc_type="bilanci")

    def test_success_json_with_text_html_content_type_decodes_base64_pdf(self) -> None:
        http = _FakeHttpClient(
            {"status": 1, "data": PDF_BASE64},
            content_type="text/html; charset=UTF-8",
        )

        result = QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type="historical")

        self.assertEqual(result.backend_status, 1)
        self.assertEqual(result.backend_state, "success")
        self.assertEqual(result.response_content_type, "text/html; charset=UTF-8")
        self.assertTrue(result.verified_pdf_magic)
        self.assertEqual(result.pdf_bytes, PDF_BYTES)
        self.assertTrue((result.base64_data_prefix or "").startswith("JVBERi0xLjQ"))
        self.assertEqual(
            result.to_summary(),
            {
                "endpoint": QKB_DOCUMENTS_ENDPOINT,
                "request_method": "POST",
                "business_nipt": "M12345678A",
                "document_type": "historical",
                "fetch_kind": "historical_extract_pdf",
                "request_payload": {"nipt": "M12345678A", "docType": "historical"},
                "http_status_code": 200,
                "backend_status": 1,
                "backend_state": "success",
                "response_content_type": "text/html; charset=UTF-8",
                "base64_data_prefix": result.base64_data_prefix,
                "verified_pdf_magic": True,
                "pdf_size_bytes": len(PDF_BYTES),
                "backend_message": None,
            },
        )

    def test_backend_status_zero_maps_to_not_found(self) -> None:
        http = _FakeHttpClient({"status": 0, "data": "No document found"})

        result = QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type="historical")

        self.assertEqual(result.backend_status, 0)
        self.assertEqual(result.backend_state, "not_found")
        self.assertFalse(result.verified_pdf_magic)
        self.assertIsNone(result.pdf_bytes)
        self.assertEqual(result.backend_message, "No document found")

    def test_backend_status_below_zero_maps_to_server_error(self) -> None:
        http = _FakeHttpClient({"status": -1, "message": "Server error"})

        result = QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type="historical")

        self.assertEqual(result.backend_status, -1)
        self.assertEqual(result.backend_state, "server_error")
        self.assertFalse(result.verified_pdf_magic)
        self.assertIsNone(result.pdf_bytes)
        self.assertEqual(result.backend_message, "Server error")

    def test_malformed_json_is_rejected(self) -> None:
        http = _FakeHttpClient("<html>not json</html>")

        with self.assertRaises(QkbDocumentResponseError):
            QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type="historical")

    def test_success_with_non_pdf_base64_is_rejected(self) -> None:
        encoded_text = base64.b64encode(b"not a pdf").decode("ascii")
        http = _FakeHttpClient({"status": 1, "data": encoded_text})

        with self.assertRaises(QkbDocumentResponseError):
            QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type="historical")

    def test_successful_pdf_can_be_saved_as_raw_fetch_without_schema_changes(self) -> None:
        http = _FakeHttpClient({"status": 1, "data": PDF_BASE64})
        result = QkbDocumentClient(http).fetch_one(nipt="M12345678A", doc_type="historical")

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)

            with session_factory() as db:
                raw_fetch = QkbDocumentCollector().save_pdf_result(db, result)
                db.commit()

                saved = db.scalar(select(RawFetch).where(RawFetch.id == raw_fetch.id))

        assert saved is not None
        self.assertEqual(saved.source_name, "qkb_documents")
        self.assertEqual(saved.fetch_kind, "historical_extract_pdf")
        self.assertEqual(saved.source_url, QKB_DOCUMENTS_ENDPOINT)
        self.assertEqual(saved.content_type, "application/pdf")
        self.assertTrue(saved.storage_path.endswith(".pdf"))
        self.assertEqual(saved.extra_metadata["business_nipt"], "M12345678A")
        self.assertEqual(saved.extra_metadata["document_type"], "historical")
        self.assertEqual(saved.extra_metadata["fetch_kind"], "historical_extract_pdf")
        self.assertEqual(saved.extra_metadata["request_payload"], {"nipt": "M12345678A", "docType": "historical"})
        self.assertEqual(saved.extra_metadata["http_status_code"], 200)
        self.assertEqual(saved.extra_metadata["backend_status"], 1)
        self.assertTrue(saved.extra_metadata["verified_pdf_magic"])
        self.assertEqual(saved.extra_metadata["pdf_size_bytes"], len(PDF_BYTES))

    def test_experimental_cli_help_mentions_single_document_options(self) -> None:
        runner = CliRunner()

        result = runner.invoke(app, ["experimental", "qkb-document-fetch-one", "--help"])
        clean_stdout = _strip_ansi(result.stdout).lower()

        self.assertEqual(result.exit_code, 0)
        self.assertIn("nipt", clean_stdout)
        self.assertIn("doc-type", clean_stdout)
        self.assertIn("save", clean_stdout)
        self.assertNotIn("batch", clean_stdout)

    def test_experimental_cli_no_save_reports_probe_metadata_without_database_write(self) -> None:
        fake_result = QkbDocumentClient(_FakeHttpClient({"status": 1, "data": PDF_BASE64})).fetch_one(
            nipt="M12345678A",
            doc_type="historical",
        )
        runner = CliRunner()

        with (
            patch("albiz_collector.cli.QkbDocumentClient") as client_cls,
            patch("albiz_collector.cli.SessionLocal", side_effect=AssertionError("database session opened")),
        ):
            client_cls.return_value.fetch_one.return_value = fake_result

            result = runner.invoke(
                app,
                [
                    "experimental",
                    "qkb-document-fetch-one",
                    "--nipt",
                    "M12345678A",
                    "--doc-type",
                    "historical",
                    "--no-save",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        client_cls.return_value.fetch_one.assert_called_once_with(nipt="M12345678A", doc_type="historical")
        summary = json.loads(result.stdout)
        self.assertEqual(summary["fetch_kind"], "historical_extract_pdf")
        self.assertEqual(summary["request_payload"], {"nipt": "M12345678A", "docType": "historical"})
        self.assertEqual(summary["http_status_code"], 200)
        self.assertFalse(summary["save_requested"])
        self.assertFalse(summary["saved"])
        self.assertIsNone(summary["save_skipped_reason"])
        self.assertIsNone(summary["raw_fetch_id"])


if __name__ == "__main__":
    unittest.main()
