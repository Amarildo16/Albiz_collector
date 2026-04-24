from __future__ import annotations

"""Offline helpers for reading QKB document action evidence from saved HTML."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class QkbDocumentActionEvidence:
    """Document action metadata confirmed by saved frontend markup."""

    document_types: tuple[str, ...]
    references_fetch_and_display_pdf: bool
    references_download_button_press: bool
    full_url: str | None
    pdf_endpoint: str | None = None


def parse_qkb_document_action_evidence(html: str | bytes) -> QkbDocumentActionEvidence:
    """Extract QKB modal document action evidence without inferring endpoints."""

    page = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    soup = BeautifulSoup(page, "lxml")

    document_types = _dedupe_preserving_order(
        value.strip()
        for value in (
            element.get("data-doc", "")
            for element in soup.select("#docPills [data-doc], [data-doc]")
        )
        if value.strip()
    )

    return QkbDocumentActionEvidence(
        document_types=tuple(document_types),
        references_fetch_and_display_pdf=bool(re.search(r"\bfetchAndDisplayPDF\s*\(", page)),
        references_download_button_press=bool(re.search(r"\bdownloadButtonPress\s*\(", page)),
        full_url=_extract_full_url(page),
        pdf_endpoint=None,
    )


def _extract_full_url(page: str) -> str | None:
    assignments = re.findall(r"\bfullUrl\s*=\s*(['\"])(.*?)\1", page)
    for _quote, value in reversed(assignments):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
