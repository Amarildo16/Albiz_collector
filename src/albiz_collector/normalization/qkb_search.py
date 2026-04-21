from __future__ import annotations

from typing import Any

from ..models import NormalizedQkbSearchRow, StructuredRecord
from ..utils.time import utc_now_naive
from .common import coerce_bool, compact_text, parse_date_value


def build_normalized_qkb_search_rows(structured_record: StructuredRecord) -> list[NormalizedQkbSearchRow]:
    payload = structured_record.payload or {}
    response = payload.get("response")
    if isinstance(response, dict):
        response = response.get("data")
    if not isinstance(response, list):
        raise ValueError("QKB search structured snapshot does not contain a list-like response")

    materialized_at = utc_now_naive()
    normalized_rows: list[NormalizedQkbSearchRow] = []
    for result_ordinal, item in enumerate(response, start=1):
        if not isinstance(item, dict):
            continue

        normalized_rows.append(
            NormalizedQkbSearchRow(
                structured_record_id=structured_record.id,
                raw_fetch_id=payload.get("raw_fetch_id"),
                snapshot_external_key=structured_record.external_key,
                source_name=structured_record.source_name,
                source_url=structured_record.source_url,
                materialized_at=materialized_at,
                result_ordinal=result_ordinal,
                search_nipt=compact_text(payload.get("nipt")),
                search_date_from=parse_date_value(payload.get("data_nga")),
                search_date_to=parse_date_value(payload.get("data_ne")),
                business_nipt=compact_text(item.get("nipti")),
                business_name=compact_text(item.get("emriISubjektit")),
                trade_name=compact_text(item.get("emriTregtar")),
                legal_form=compact_text(item.get("formaLigjore")),
                registration_date=parse_date_value(item.get("dataERegjistrimit")),
                city=compact_text(item.get("qyteti")),
                ownership_text=compact_text(item.get("shtetesia")),
                subject_status=compact_text(item.get("statusiISubjektit")),
                subject_type=compact_text(item.get("tipiISubjektit")),
                activity_text=compact_text(item.get("sektoriIVeprimtarise")),
                administrators_text=compact_text(item.get("adminOrtakAksionar")),
                has_red_flags=coerce_bool(item.get("showRedFlag")),
                source_payload=item,
            )
        )
    return normalized_rows