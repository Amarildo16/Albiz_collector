from __future__ import annotations

from sqlalchemy import or_

from ..models import RawFetch


CONTENT_HASH_MISMATCH_REASON = "content_hash mismatch"
MISSING_FILE_REASON = "missing file"

ISSUE_TYPE_TO_REASON = {
    "content_hash_mismatch": CONTENT_HASH_MISMATCH_REASON,
    "missing_file": MISSING_FILE_REASON,
}


def corruption_reason_for_issue_type(issue_type: str) -> str:
    return ISSUE_TYPE_TO_REASON.get(issue_type, issue_type.replace("_", " "))


def assert_raw_fetch_is_trusted(raw_fetch: RawFetch) -> None:
    if raw_fetch.is_corrupted:
        reason = raw_fetch.corruption_reason or "unknown corruption reason"
        raise ValueError(f"raw fetch {raw_fetch.id} is marked corrupted: {reason}")


def exclude_corrupted_raw_fetches(statement, row_model):
    return statement.outerjoin(RawFetch, row_model.raw_fetch_id == RawFetch.id).where(
        or_(row_model.raw_fetch_id.is_(None), RawFetch.is_corrupted.is_(False))
    )
