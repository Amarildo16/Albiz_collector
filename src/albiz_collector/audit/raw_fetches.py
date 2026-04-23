from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RawFetch
from ..utils.hashing import sha256_bytes
from ..utils.raw_fetches import corruption_reason_for_issue_type
from ..utils.storage import resolve_storage_path


def inventory_raw_fetch_integrity(
    db: Session,
    *,
    source_name: str | None = None,
    limit: int | None = None,
    corrupted_only: bool = False,
    mark_corrupted: bool = False,
) -> dict[str, Any]:
    statement = select(RawFetch).order_by(RawFetch.id)
    if source_name is not None:
        statement = statement.where(RawFetch.source_name == source_name)

    rows = db.scalars(statement).all()
    issues: list[dict[str, Any]] = []
    missing_file_count = 0
    content_hash_mismatch_count = 0
    corrupted_rows_before_scan = sum(1 for row in rows if row.is_corrupted)
    rows_marked_corrupted = 0
    unhealthy_row_ids: set[int] = {row.id for row in rows if row.is_corrupted}

    for row in rows:
        resolved_path = resolve_storage_path(row.storage_path)
        issue_type: str | None = None
        actual_content_hash: str | None = None
        if not resolved_path.exists():
            missing_file_count += 1
            issue_type = "missing_file"
        else:
            actual_content_hash = sha256_bytes(resolved_path.read_bytes())
            if actual_content_hash != row.content_hash:
                issue_type = "content_hash_mismatch"

        if issue_type == "content_hash_mismatch":
            content_hash_mismatch_count += 1

        detected_reason = (
            corruption_reason_for_issue_type(issue_type) if issue_type is not None else None
        )
        if issue_type is not None:
            unhealthy_row_ids.add(row.id)
            if mark_corrupted and (
                not row.is_corrupted or row.corruption_reason != detected_reason
            ):
                row.is_corrupted = True
                row.corruption_reason = detected_reason
                rows_marked_corrupted += 1

        row_is_corrupted = row.is_corrupted or (
            mark_corrupted and issue_type is not None
        )
        row_corruption_reason = row.corruption_reason or detected_reason
        if row_is_corrupted:
            unhealthy_row_ids.add(row.id)

        if issue_type is None and not (corrupted_only and row_is_corrupted):
            continue

        issues.append(
            {
                "raw_fetch_id": row.id,
                "source_name": row.source_name,
                "fetch_kind": row.fetch_kind,
                "fetched_at": row.fetched_at,
                "source_url": row.source_url,
                "storage_path": row.storage_path,
                "resolved_path": str(resolved_path),
                "issue_type": issue_type or "marked_corrupted",
                "detected_issue_type": issue_type,
                "reason": detected_reason or row_corruption_reason,
                "stored_content_hash": row.content_hash,
                "actual_content_hash": actual_content_hash,
                "is_corrupted": row_is_corrupted,
                "corruption_reason": row_corruption_reason,
            }
        )

    if mark_corrupted and rows_marked_corrupted > 0:
        db.commit()

    total_issue_count = missing_file_count + content_hash_mismatch_count
    corrupted_rows_after_scan = sum(1 for row in rows if row.is_corrupted)
    if limit is not None:
        issues = issues[:limit]

    return {
        "dataset": "raw_fetch_integrity",
        "source_name": source_name,
        "rows_scanned": len(rows),
        "healthy_rows": len(rows) - len(unhealthy_row_ids),
        "issues_found": total_issue_count,
        "content_hash_mismatch_count": content_hash_mismatch_count,
        "missing_file_count": missing_file_count,
        "corrupted_rows_before_scan": corrupted_rows_before_scan,
        "corrupted_rows_after_scan": corrupted_rows_after_scan,
        "rows_marked_corrupted": rows_marked_corrupted,
        "corrupted_only": corrupted_only,
        "mark_corrupted": mark_corrupted,
        "limit": limit,
        "returned_issue_count": len(issues),
        "issues_truncated": limit is not None and len(issues) < (
            corrupted_rows_after_scan if corrupted_only else total_issue_count
        ),
        "issues": issues,
    }
