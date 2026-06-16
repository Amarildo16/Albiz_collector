from __future__ import annotations

import csv
import io
import re

from ..models import NormalizedAppExportRow, RawFetch, StructuredRecord
from ..utils.time import utc_now_naive
from .common import compact_text, parse_date_value, parse_decimal_value, parse_yes_no_flag


NIPT_PATTERN = re.compile(r"\b[A-Z][0-9]{8}[A-Z]\b", re.IGNORECASE)


def extract_nipts(value: str | None) -> list[str]:
    if value is None:
        return []

    seen: set[str] = set()
    nipts: list[str] = []
    for match in NIPT_PATTERN.findall(value):
        nipt = match.upper()
        if nipt not in seen:
            seen.add(nipt)
            nipts.append(nipt)
    return nipts


def normalize_single_winner_nipt(value: str | None) -> str | None:
    nipts = extract_nipts(value)
    if len(nipts) == 1:
        return nipts[0]
    return None


def parse_app_export_csv(content: bytes) -> list[dict[str, str]]:
    decoded = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(decoded))
    return [{key: value or "" for key, value in row.items()} for row in reader]


def build_normalized_app_export_rows(
    structured_record: StructuredRecord,
    raw_fetch: RawFetch,
    csv_content: bytes,
) -> list[NormalizedAppExportRow]:
    payload = structured_record.payload or {}
    export_year = payload.get("year")
    if not isinstance(export_year, int):
        try:
            export_year = int(structured_record.external_key)
        except ValueError as exc:
            raise ValueError("APP structured snapshot is missing a usable export year") from exc

    materialized_at = utc_now_naive()
    normalized_rows: list[NormalizedAppExportRow] = []
    for row_ordinal, row in enumerate(parse_app_export_csv(csv_content), start=1):
        normalized_rows.append(
            NormalizedAppExportRow(
                structured_record_id=structured_record.id,
                raw_fetch_id=raw_fetch.id,
                snapshot_external_key=structured_record.external_key,
                source_name=structured_record.source_name,
                source_url=structured_record.source_url or raw_fetch.source_url,
                materialized_at=materialized_at,
                export_year=export_year,
                row_ordinal=row_ordinal,
                procurement_reference=compact_text(row.get("Numri_i_references")),
                contracting_authority=compact_text(row.get("Autoriteti_kontraktues")),
                procurement_subject=compact_text(row.get("Objekti_i_prokurimit")),
                procedure_type=compact_text(row.get("Lloji_i_procedures")),
                contract_type=compact_text(row.get("Tipi_i_kontrates")),
                publication_date=parse_date_value(row.get("Data_e_publikimit")),
                opening_date=parse_date_value(row.get("Data_e_hapjes")),
                closing_date=parse_date_value(row.get("Data_e_mbylljes")),
                is_cancelled=parse_yes_no_flag(row.get("Anulluar")),
                is_suspended=parse_yes_no_flag(row.get("Pezulluar")),
                budget_limit_amount=parse_decimal_value(row.get("Fondi_limit")),
                winner_name=compact_text(row.get("Fituesi")),
                winner_nipt=normalize_single_winner_nipt(row.get("NIPT_i_fituesit")),
                winner_value_amount=parse_decimal_value(row.get("Vlera_e_fituesit")),
                cpv_codes=compact_text(row.get("Kodet_CPV")),
                source_payload=row,
            )
        )
    return normalized_rows
