from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    NormalizedAppExportRow,
    NormalizedQkbSearchRow,
    RawFetch,
    StructuredRecord,
)
from ..utils.raw_fetches import assert_raw_fetch_is_trusted
from ..utils.storage import read_storage_bytes
from .app_exports import build_normalized_app_export_rows
from .qkb_search import build_normalized_qkb_search_rows


class CorruptedRawFetchError(ValueError):
    """Raised when a structured snapshot points to a quarantined raw fetch."""


def _base_stats(dataset: str, records: list[StructuredRecord]) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "snapshots_seen": len(records),
        "snapshots_materialized": 0,
        "snapshots_skipped_corrupted": 0,
        "snapshots_failed": 0,
        "rows_deleted_before_insert": 0,
        "rows_inserted": 0,
        "rows_materialized": 0,
        "skipped": [],
        "errors": [],
    }


def _raw_fetch_for_snapshot(db: Session, record: StructuredRecord) -> RawFetch:
    payload = record.payload or {}
    raw_fetch_id = payload.get("raw_fetch_id")
    if not isinstance(raw_fetch_id, int):
        raise ValueError("structured snapshot is missing raw_fetch_id")

    raw_fetch = db.get(RawFetch, raw_fetch_id)
    if raw_fetch is None:
        raise ValueError(f"raw fetch {raw_fetch_id} not found")
    try:
        assert_raw_fetch_is_trusted(raw_fetch)
    except ValueError as exc:
        raise CorruptedRawFetchError(str(exc)) from exc
    return raw_fetch


def materialize_app_exports(db: Session) -> dict[str, Any]:
    records = db.scalars(
        select(StructuredRecord)
        .where(
            StructuredRecord.source_name == "app_exports",
            StructuredRecord.record_type == "procurement_export_year",
        )
        .order_by(StructuredRecord.id)
    ).all()

    stats = _base_stats("app_exports", records)

    for record in records:
        try:
            raw_fetch = _raw_fetch_for_snapshot(db, record)
            csv_content = read_storage_bytes(raw_fetch.storage_path)
            normalized_rows = build_normalized_app_export_rows(record, raw_fetch, csv_content)

            delete_result = db.execute(
                delete(NormalizedAppExportRow).where(
                    NormalizedAppExportRow.structured_record_id == record.id
                )
            )
            db.add_all(normalized_rows)
            db.commit()
            stats["snapshots_materialized"] += 1
            stats["rows_deleted_before_insert"] += delete_result.rowcount or 0
            stats["rows_inserted"] += len(normalized_rows)
            stats["rows_materialized"] += len(normalized_rows)
        except CorruptedRawFetchError as exc:
            db.rollback()
            stats["snapshots_skipped_corrupted"] += 1
            stats["skipped"].append({"structured_record_id": record.id, "reason": str(exc)})
        except Exception as exc:
            db.rollback()
            stats["snapshots_failed"] += 1
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

    stats = _base_stats("qkb_search", records)

    for record in records:
        try:
            raw_fetch = _raw_fetch_for_snapshot(db, record)
            normalized_rows = build_normalized_qkb_search_rows(record)
            for row in normalized_rows:
                row.raw_fetch_id = raw_fetch.id
                if row.source_url is None:
                    row.source_url = raw_fetch.source_url

            delete_result = db.execute(
                delete(NormalizedQkbSearchRow).where(
                    NormalizedQkbSearchRow.structured_record_id == record.id
                )
            )
            db.add_all(normalized_rows)
            db.commit()
            stats["snapshots_materialized"] += 1
            stats["rows_deleted_before_insert"] += delete_result.rowcount or 0
            stats["rows_inserted"] += len(normalized_rows)
            stats["rows_materialized"] += len(normalized_rows)
        except CorruptedRawFetchError as exc:
            db.rollback()
            stats["snapshots_skipped_corrupted"] += 1
            stats["skipped"].append({"structured_record_id": record.id, "reason": str(exc)})
        except Exception as exc:
            db.rollback()
            stats["snapshots_failed"] += 1
            stats["errors"].append({"structured_record_id": record.id, "error": str(exc)})

    return stats


def materialize_all(db: Session) -> dict[str, Any]:
    return {
        "app_exports": materialize_app_exports(db),
        "qkb_search": materialize_qkb_search(db),
    }
