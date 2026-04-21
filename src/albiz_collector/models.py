from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .utils.time import utc_now_naive


class RawFetch(Base):
    """Immutable raw fetch metadata for persisted on-disk artifacts."""

    __tablename__ = "raw_fetches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    fetch_kind: Mapped[str] = mapped_column(String(50), index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(Text)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)


class StructuredRecord(Base):
    """Latest normalized snapshot per logical external record key."""

    __tablename__ = "structured_records"
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "record_type",
            "external_key",
            name="uq_source_record_external_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    record_type: Mapped[str] = mapped_column(String(100), index=True)
    external_key: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)


class NormalizedAppExportRow(Base):
    __tablename__ = "normalized_app_export_rows"
    __table_args__ = (
        UniqueConstraint(
            "structured_record_id",
            "row_ordinal",
            name="uq_normalized_app_export_snapshot_row",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    structured_record_id: Mapped[int] = mapped_column(
        ForeignKey("structured_records.id"),
        index=True,
    )
    raw_fetch_id: Mapped[int | None] = mapped_column(ForeignKey("raw_fetches.id"), nullable=True, index=True)
    snapshot_external_key: Mapped[str] = mapped_column(String(255), index=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    materialized_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    export_year: Mapped[int] = mapped_column(Integer, index=True)
    row_ordinal: Mapped[int] = mapped_column(Integer)
    procurement_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    contracting_authority: Mapped[str | None] = mapped_column(Text, nullable=True)
    procurement_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    procedure_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_cancelled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_suspended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    budget_limit_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    winner_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_nipt: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    winner_value_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    cpv_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class NormalizedQkbSearchRow(Base):
    __tablename__ = "normalized_qkb_search_rows"
    __table_args__ = (
        UniqueConstraint(
            "structured_record_id",
            "result_ordinal",
            name="uq_normalized_qkb_search_snapshot_result",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    structured_record_id: Mapped[int] = mapped_column(
        ForeignKey("structured_records.id"),
        index=True,
    )
    raw_fetch_id: Mapped[int | None] = mapped_column(ForeignKey("raw_fetches.id"), nullable=True, index=True)
    snapshot_external_key: Mapped[str] = mapped_column(String(255), index=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    materialized_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    result_ordinal: Mapped[int] = mapped_column(Integer)
    search_nipt: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    search_date_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    search_date_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    business_nipt: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    business_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    trade_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_form: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ownership_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    administrators_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_red_flags: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
