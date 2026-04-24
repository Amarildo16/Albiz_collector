from __future__ import annotations

"""Experimental one-NIPT QKB subject document fetch helpers."""

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from ..models import RawFetch
from ..utils.http import HttpClient, ResponsePayload
from .base import CollectorBase

QKB_DOCUMENTS_ENDPOINT = (
    "https://format.qkb.gov.al/wp-content/themes/twentytwentyfive-child/modules/search/"
    "national-registry/subject/search-for-subject-get-documents.php"
)
QKB_DOCUMENT_REQUEST_METHOD = "POST"
QKB_DOCUMENT_REQUEST_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://format.qkb.gov.al",
    "Referer": "https://format.qkb.gov.al/kerko-per-subjekt/",
}
ALLOWED_QKB_DOCUMENT_TYPES = ("historical", "simple", "rpp")
QKB_DOCUMENT_FETCH_KINDS = {
    "historical": "historical_extract_pdf",
    "simple": "simple_extract_pdf",
    "rpp": "rpp_pdf",
}
PDF_MAGIC = b"%PDF"
BASE64_PREFIX_LENGTH = 16

BackendState = Literal["success", "not_found", "server_error"]


class QkbDocumentError(Exception):
    """Base error for experimental QKB document handling."""


class QkbDocumentResponseError(QkbDocumentError):
    """Raised when QKB returns a response that cannot be safely interpreted."""


@dataclass(frozen=True)
class QkbDocumentFetchResult:
    endpoint: str
    request_method: str
    business_nipt: str
    document_type: str
    request_payload: dict[str, str]
    http_status_code: int
    response_content_type: str | None
    backend_status: int
    backend_state: BackendState
    base64_data_prefix: str | None
    verified_pdf_magic: bool
    pdf_bytes: bytes | None = None
    backend_message: str | None = None

    @property
    def pdf_size_bytes(self) -> int | None:
        if self.pdf_bytes is None:
            return None
        return len(self.pdf_bytes)

    def to_summary(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "request_method": self.request_method,
            "business_nipt": self.business_nipt,
            "document_type": self.document_type,
            "backend_status": self.backend_status,
            "backend_state": self.backend_state,
            "response_content_type": self.response_content_type,
            "base64_data_prefix": self.base64_data_prefix,
            "verified_pdf_magic": self.verified_pdf_magic,
            "pdf_size_bytes": self.pdf_size_bytes,
            "backend_message": self.backend_message,
        }


class QkbDocumentClient:
    """Small client for the confirmed one-NIPT QKB document endpoint."""

    def __init__(self, http_client: Any | None = None) -> None:
        self._http_client = http_client

    def fetch_one(self, *, nipt: str, doc_type: str) -> QkbDocumentFetchResult:
        payload = build_qkb_document_request_payload(nipt=nipt, doc_type=doc_type)

        if self._http_client is not None:
            response = self._http_client.post(
                QKB_DOCUMENTS_ENDPOINT,
                data=payload,
                headers=QKB_DOCUMENT_REQUEST_HEADERS,
            )
        else:
            with HttpClient() as http:
                response = http.post(
                    QKB_DOCUMENTS_ENDPOINT,
                    data=payload,
                    headers=QKB_DOCUMENT_REQUEST_HEADERS,
                )

        return parse_qkb_document_response(
            response,
            business_nipt=payload["nipt"],
            document_type=payload["docType"],
            request_payload=payload,
        )


class QkbDocumentCollector(CollectorBase):
    """Experimental storage wrapper for a single validated QKB document PDF."""

    source_name = "qkb_documents"

    def save_pdf_result(self, db: Session, result: QkbDocumentFetchResult) -> RawFetch:
        if result.backend_state != "success" or result.pdf_bytes is None:
            raise ValueError("Only successful QKB document PDF results can be saved")

        fetch_kind = fetch_kind_for_doc_type(result.document_type)
        filename = f"{_safe_filename_component(result.business_nipt)}-{result.document_type}.pdf"
        return self.save_raw_fetch(
            db,
            url=result.endpoint,
            content=result.pdf_bytes,
            fetch_kind=fetch_kind,
            status_code=result.http_status_code,
            content_type="application/pdf",
            filename=filename,
            extra_metadata={
                "business_nipt": result.business_nipt,
                "document_type": result.document_type,
                "endpoint": result.endpoint,
                "request_method": result.request_method,
                "request_payload": result.request_payload,
                "backend_status": result.backend_status,
                "backend_state": result.backend_state,
                "response_content_type": result.response_content_type,
                "base64_data_prefix": result.base64_data_prefix,
                "verified_pdf_magic": result.verified_pdf_magic,
            },
        )


def build_qkb_document_request_payload(*, nipt: str, doc_type: str) -> dict[str, str]:
    normalized_nipt = nipt.strip().upper()
    if not normalized_nipt:
        raise ValueError("NIPT must not be empty")

    normalized_doc_type = normalize_qkb_document_type(doc_type)
    return {
        "nipt": normalized_nipt,
        "docType": normalized_doc_type,
    }


def normalize_qkb_document_type(doc_type: str) -> str:
    normalized = doc_type.strip().lower()
    if normalized not in ALLOWED_QKB_DOCUMENT_TYPES:
        allowed = ", ".join(ALLOWED_QKB_DOCUMENT_TYPES)
        raise ValueError(f"Unsupported QKB document type {doc_type!r}; allowed values: {allowed}")
    return normalized


def fetch_kind_for_doc_type(doc_type: str) -> str:
    return QKB_DOCUMENT_FETCH_KINDS[normalize_qkb_document_type(doc_type)]


def parse_qkb_document_response(
    response: ResponsePayload,
    *,
    business_nipt: str,
    document_type: str,
    request_payload: dict[str, str],
) -> QkbDocumentFetchResult:
    payload = _load_json_response(response)
    backend_status = _extract_backend_status(payload)
    backend_message = _extract_backend_message(payload, include_data=backend_status <= 0)

    if backend_status == 0:
        return _build_result(
            response,
            business_nipt=business_nipt,
            document_type=document_type,
            request_payload=request_payload,
            backend_status=backend_status,
            backend_state="not_found",
            backend_message=backend_message,
        )

    if backend_status < 0:
        return _build_result(
            response,
            business_nipt=business_nipt,
            document_type=document_type,
            request_payload=request_payload,
            backend_status=backend_status,
            backend_state="server_error",
            backend_message=backend_message,
        )

    encoded_data = payload.get("data")
    if not isinstance(encoded_data, str) or not encoded_data.strip():
        raise QkbDocumentResponseError("QKB document response status was successful but data was missing")

    normalized_base64 = "".join(encoded_data.split())
    try:
        pdf_bytes = base64.b64decode(normalized_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise QkbDocumentResponseError("QKB document data was not valid base64") from exc

    if not pdf_bytes.startswith(PDF_MAGIC):
        raise QkbDocumentResponseError("Decoded QKB document bytes did not start with %PDF")

    return _build_result(
        response,
        business_nipt=business_nipt,
        document_type=document_type,
        request_payload=request_payload,
        backend_status=backend_status,
        backend_state="success",
        backend_message=backend_message,
        base64_data_prefix=normalized_base64[:BASE64_PREFIX_LENGTH],
        verified_pdf_magic=True,
        pdf_bytes=pdf_bytes,
    )


def _load_json_response(response: ResponsePayload) -> dict[str, Any]:
    text = response.text
    if text is None:
        text = response.content.decode("utf-8", errors="replace")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QkbDocumentResponseError("QKB document response body was not valid JSON") from exc

    if not isinstance(payload, dict):
        raise QkbDocumentResponseError("QKB document response JSON was not an object")
    return payload


def _extract_backend_status(payload: dict[str, Any]) -> int:
    raw_status = payload.get("status")
    if isinstance(raw_status, bool) or raw_status is None:
        raise QkbDocumentResponseError("QKB document response did not include a numeric status")

    try:
        return int(raw_status)
    except (TypeError, ValueError) as exc:
        raise QkbDocumentResponseError("QKB document response status was not numeric") from exc


def _extract_backend_message(payload: dict[str, Any], *, include_data: bool) -> str | None:
    keys = ("message", "error", "data") if include_data else ("message", "error")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _build_result(
    response: ResponsePayload,
    *,
    business_nipt: str,
    document_type: str,
    request_payload: dict[str, str],
    backend_status: int,
    backend_state: BackendState,
    backend_message: str | None,
    base64_data_prefix: str | None = None,
    verified_pdf_magic: bool = False,
    pdf_bytes: bytes | None = None,
) -> QkbDocumentFetchResult:
    return QkbDocumentFetchResult(
        endpoint=QKB_DOCUMENTS_ENDPOINT,
        request_method=QKB_DOCUMENT_REQUEST_METHOD,
        business_nipt=business_nipt,
        document_type=normalize_qkb_document_type(document_type),
        request_payload=dict(request_payload),
        http_status_code=response.status_code,
        response_content_type=response.content_type,
        backend_status=backend_status,
        backend_state=backend_state,
        base64_data_prefix=base64_data_prefix,
        verified_pdf_magic=verified_pdf_magic,
        pdf_bytes=pdf_bytes,
        backend_message=backend_message,
    )


def _safe_filename_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return safe.strip("_") or "qkb-document"
