from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RawFetch, StructuredRecord
from ..utils.hashing import sha256_bytes
from ..utils.storage import build_storage_path, write_bytes
from ..utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class CollectorBase:
    source_name = "base"

    def save_raw_fetch(
        self,
        db: Session,
        *,
        url: str,
        content: bytes,
        fetch_kind: str,
        status_code: int | None,
        content_type: str | None,
        extra_metadata: dict[str, Any] | None = None,
        filename: str | None = None,
    ) -> RawFetch:
        content_hash = sha256_bytes(content)
        extension = self._guess_extension(content_type, url)
        filename = self._build_storage_filename(
            requested_filename=filename,
            content_hash=content_hash,
            extension=extension,
        )
        storage_path = build_storage_path(self.source_name, fetch_kind, filename)
        write_bytes(storage_path, content)

        row = RawFetch(
            source_name=self.source_name,
            source_url=url,
            fetch_kind=fetch_kind,
            status_code=status_code,
            content_type=content_type,
            content_hash=content_hash,
            storage_path=str(storage_path),
            extra_metadata=extra_metadata,
        )
        db.add(row)
        db.flush()
        return row

    def upsert_structured_record(
        self,
        db: Session,
        *,
        record_type: str,
        external_key: str,
        title: str | None,
        source_url: str | None,
        content_hash: str,
        payload: dict[str, Any] | None,
        published_at: datetime | None = None,
        company_name: str | None = None,
        external_id: str | None = None,
    ) -> StructuredRecord:
        record = db.scalar(
            select(StructuredRecord).where(
                StructuredRecord.source_name == self.source_name,
                StructuredRecord.record_type == record_type,
                StructuredRecord.external_key == external_key,
            )
        )

        now = utc_now_naive()
        if record is None:
            record = StructuredRecord(
                source_name=self.source_name,
                record_type=record_type,
                external_key=external_key,
                title=title,
                source_url=source_url,
                published_at=published_at,
                company_name=company_name,
                external_id=external_id,
                content_hash=content_hash,
                payload=payload,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(record)
        else:
            record.title = title
            record.source_url = source_url
            record.published_at = published_at
            record.company_name = company_name
            record.external_id = external_id
            record.content_hash = content_hash
            record.payload = payload
            record.last_seen_at = now

        db.flush()
        return record

    @staticmethod
    def _guess_extension(content_type: str | None, url: str) -> str:
        if url.endswith(".csv") or "csv" in (content_type or ""):
            return ".csv"
        if url.endswith(".pdf") or "pdf" in (content_type or ""):
            return ".pdf"
        if url.endswith(".json") or "json" in (content_type or ""):
            return ".json"
        return ".html"

    @staticmethod
    def _build_storage_filename(
        *,
        requested_filename: str | None,
        content_hash: str,
        extension: str,
    ) -> str:
        if requested_filename is None:
            return f"{content_hash}{extension}"

        original = Path(requested_filename)
        suffix = original.suffix or extension
        stem = original.stem or content_hash
        return f"{stem}-{content_hash}{suffix}"

    @staticmethod
    def dump_json_bytes(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
