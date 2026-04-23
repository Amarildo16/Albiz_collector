from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import QkbSearchRun


def list_qkb_search_runs(
    db: Session,
    *,
    status: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    statement = select(QkbSearchRun).order_by(QkbSearchRun.id.desc())
    if status is not None:
        statement = statement.where(QkbSearchRun.status == status)

    rows = db.scalars(statement).all()
    if limit is not None:
        rows = rows[:limit]

    return {
        "dataset": "qkb_search_runs",
        "status_filter": status,
        "limit": limit,
        "returned_run_count": len(rows),
        "runs": [
            {
                "id": row.id,
                "collector_name": row.collector_name,
                "mode": row.mode,
                "date_from": row.date_from,
                "date_to": row.date_to,
                "current_date": row.current_date,
                "status": row.status,
                "started_at": row.started_at,
                "updated_at": row.updated_at,
                "completed_at": row.completed_at,
                "last_error": row.last_error,
            }
            for row in rows
        ],
    }
