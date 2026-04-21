from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    NormalizedAppExportRow,
    NormalizedQkbSearchRow,
    RawFetch,
    StructuredRecord,
)
from .app_exports import build_normalized_app_export_rows
from .qkb_search import build_normalized_qkb_search_rows


def materialize_app_exports(db: Session) -> dict[str, Any]:
    records = db.scalars(
        select(StructuredRecord)
        .where(
            StructuredRecord.source_name == "app_exports",
            StructuredRecord.record_type == "procurement_export_year",
        )
        .order_by(StructuredRecord.id)
    ).all()

    stats: dict[str, Any] = {
        "dataset": "app_exports",
        "snapshots_seen": len(records),
        "snapshots_materialized": 0,
        "rows_materialized": 0,
        "errors": [],
    }

    for record in records:
        payload = record.payload or {}
        raw_fetch_id = payload.get("raw_fetch_id")
        try:
            if not isinstance(raw_fetch_id, int):
                raise ValueError("structured snapshot is missing raw_fetch_id")
            raw_fetch = db.get(RawFetch, raw_fetch_id)
            if raw_fetch is None:
                raise ValueError(f"raw fetch {raw_fetch_id} not found")
            csv_content = Path(raw_fetch.storage_path).read_bytes()
            normalized_rows = build_normalized_app_export_rows(record, raw_fetch, csv_content)

            db.execute(
                delete(NormalizedAppExportRow).where(
                    NormalizedAppExportRow.structured_record_id == record.id
                )
            )
            db.add_all(normalized_rows)
            db.commit()
            stats["snapshots_materialized"] += 1
            stats["rows_materialized"] += len(normalized_rows)
        except Exception as exc:
            db.rollback()
            stats["errors"].append({"structured_record_id": record.id, "error": str(exc)})

    return stats


def materialize_qkb_search(db: Session) -> dict[str, Any]:
    records = db.scalars(
        select(StructuredRecord)
        .where(
            StructuredRecord.source_name == "qkb_search",
            StructuredRecord.record_type == "qkb_search_snapshot",
        )
        .order_by(StructuredRecord.id)
    ).all()

    stats: dict[str, Any] = {
        "dataset": "qkb_search",
        "snapshots_seen": len(records),
        "snapshots_materialized": 0,
        "rows_materialized": 0,
        "errors": [],
    }

    for record in records:
        try:
            normalized_rows = build_normalized_qkb_search_rows(record)
            db.execute(
                delete(NormalizedQkbSearchRow).where(
                    NormalizedQkbSearchRow.structured_record_id == record.id
                )
            )
            db.add_all(normalized_rows)
            db.commit()
            stats["snapshots_materialized"] += 1
            stats["rows_materialized"] += len(normalized_rows)
        except Exception as exc:
            db.rollback()
            stats["errors"].append({"structured_record_id": record.id, "error": str(exc)})

    return stats


def materialize_all(db: Session) -> dict[str, Any]:
    return {
        "app_exports": materialize_app_exports(db),
        "qkb_search": materialize_qkb_search(db),
    }