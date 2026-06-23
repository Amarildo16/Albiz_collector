from __future__ import annotations

"""Targeted, bounded QKB registry lookups for exact company NIPTs."""

import time
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import NormalizedQkbSearchRow, RawFetch, StructuredRecord
from ..normalization.qkb_search import build_normalized_qkb_search_rows
from ..utils.http import ResponsePayload
from ..utils.time import utc_now_naive
from .qkb_search import QkbSearchCollector


TARGETED_NIPT_LOOKUP_DATASET = "qkb_search_by_nipt"
TARGETED_NIPT_LOOKUP_SOURCE_TYPE = "qkb_targeted_nipt_lookup"
TARGETED_NIPT_LOOKUP_MODE = "targeted_nipt_lookup"
TARGETED_NIPT_LOOKUP_FETCH_KIND = "targeted_nipt_search_results_page"
DEFAULT_QKB_NIPT_LOOKUP_DELAY_SECONDS = 1.0
_EXISTING_NIPT_QUERY_CHUNK_SIZE = 500


def normalize_qkb_lookup_nipt(value: str | None) -> str | None:
    """Return the canonical uppercase identifier used for one QKB NIPT lookup."""
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def load_qkb_lookup_nipts(input_path: str | Path) -> list[str]:
    """Read one NIPT per line and return canonical, order-preserving unique values."""
    path = Path(input_path)
    values = path.read_text(encoding="utf-8-sig").splitlines()
    return _dedupe_nipts(values)


class QkbNiptLookupCollector(QkbSearchCollector):
    """Persist and immediately normalize bounded, exact-NIPT QKB search results."""

    def __init__(self, sleeper: Callable[[float], None] = time.sleep) -> None:
        self._sleeper = sleeper

    def collect(
        self,
        db: Session,
        *,
        nipt: str | None = None,
        input_path: str | Path | None = None,
        limit: int = 100,
        offset: int = 0,
        delay_seconds: float = DEFAULT_QKB_NIPT_LOOKUP_DELAY_SECONDS,
        force: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        _validate_options(limit=limit, offset=offset, delay_seconds=delay_seconds)
        if (nipt is None) == (input_path is None):
            raise ValueError("Provide exactly one of nipt or input_path")

        requested_nipt = normalize_qkb_lookup_nipt(nipt)
        input_nipts = [requested_nipt] if requested_nipt is not None else load_qkb_lookup_nipts(input_path)
        input_nipts = _dedupe_nipts(input_nipts)
        selection = self._select_nipts(
            db,
            input_nipts=input_nipts,
            limit=limit,
            offset=offset,
            force=force,
        )
        started_at = time.monotonic()
        summary: dict[str, Any] = {
            "dataset": TARGETED_NIPT_LOOKUP_DATASET,
            "source_type": TARGETED_NIPT_LOOKUP_SOURCE_TYPE,
            "collection_mode": TARGETED_NIPT_LOOKUP_MODE,
            "requested_nipt": requested_nipt,
            "input_path": str(input_path) if input_path is not None else None,
            "input_nipt_count": len(input_nipts),
            "requested_limit": limit,
            "offset": offset,
            "delay_seconds": delay_seconds,
            "force": force,
            "dry_run": dry_run,
            "selected_nipts": selection["selected_nipts"],
            "selected_nipt_count": len(selection["selected_nipts"]),
            "skipped_existing": selection["skipped_existing"],
            "skipped_offset": selection["skipped_offset"],
            "processed_count": 0,
            "found_count": 0,
            "missing_count": 0,
            "rows_upserted": 0,
            "rows_materialized": 0,
            "parse_errors": 0,
            "http_errors": 0,
            "persistence_errors": 0,
            "lookup_requests_executed": 0,
            "errors": [],
        }
        if dry_run or not selection["selected_nipts"]:
            summary["elapsed_seconds"] = _elapsed_seconds(started_at)
            return summary

        try:
            with self._http_client() as http:
                session_cookies = self._establish_search_session(http)
                for index, selected_nipt in enumerate(selection["selected_nipts"]):
                    if index and delay_seconds:
                        self._sleeper(delay_seconds)

                    fetch_result = self._fetch_targeted_lookup(
                        http,
                        session_cookies=session_cookies,
                        nipt=selected_nipt,
                    )
                    summary["processed_count"] += 1
                    summary["lookup_requests_executed"] += 1

                    if fetch_result["status"] == "http_error":
                        summary["http_errors"] += 1
                        summary["errors"].append(_error_summary(selected_nipt, "http", fetch_result["error"]))
                        continue
                    if fetch_result["status"] == "parse_error":
                        summary["parse_errors"] += 1
                        summary["errors"].append(_error_summary(selected_nipt, "parse", fetch_result["error"]))
                        continue

                    if fetch_result["status"] == "found":
                        summary["found_count"] += 1
                    else:
                        summary["missing_count"] += 1

                    try:
                        persistence = self._persist_and_materialize_lookup(
                            db,
                            nipt=selected_nipt,
                            response=fetch_result["response"],
                            parsed_response=fetch_result["parsed_response"],
                            records=fetch_result["records"],
                            form_data=fetch_result["form_data"],
                            lookup_outcome=fetch_result["status"],
                        )
                        summary["rows_upserted"] += persistence["rows_materialized"]
                        summary["rows_materialized"] += persistence["rows_materialized"]
                    except Exception as exc:
                        db.rollback()
                        summary["persistence_errors"] += 1
                        summary["errors"].append(
                            _error_summary(selected_nipt, "persistence", f"{type(exc).__name__}: {exc}")
                        )
        except Exception as exc:
            db.rollback()
            summary["http_errors"] += 1
            summary["errors"].append(
                _error_summary(None, "session", f"{type(exc).__name__}: {exc}")
            )

        summary["elapsed_seconds"] = _elapsed_seconds(started_at)
        return summary

    def _select_nipts(
        self,
        db: Session,
        *,
        input_nipts: list[str],
        limit: int,
        offset: int,
        force: bool,
    ) -> dict[str, Any]:
        candidate_nipts = input_nipts[offset:]
        existing_nipts = set() if force else _existing_qkb_business_nipts(db, candidate_nipts)
        selected_nipts: list[str] = []
        skipped_existing = 0

        for candidate_nipt in candidate_nipts:
            if candidate_nipt in existing_nipts:
                skipped_existing += 1
                continue
            selected_nipts.append(candidate_nipt)
            if len(selected_nipts) >= limit:
                break

        return {
            "selected_nipts": selected_nipts,
            "skipped_existing": skipped_existing,
            "skipped_offset": min(offset, len(input_nipts)),
        }

    def _fetch_targeted_lookup(
        self,
        http: Any,
        *,
        session_cookies: Any,
        nipt: str,
    ) -> dict[str, Any]:
        form_data = self._build_form_data(nipt=nipt)
        try:
            response = self._execute_search_request(
                http,
                session_cookies=session_cookies,
                form_data=form_data,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                response = _response_payload_from_http_error(exc)
                return _missing_fetch_result(response=response, form_data=form_data)
            return _http_error_fetch_result(exc)
        except httpx.HTTPError as exc:
            return _http_error_fetch_result(exc)
        except Exception as exc:
            return {
                "status": "http_error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        if response.status_code in {404, 410}:
            return _missing_fetch_result(response=response, form_data=form_data)
        if response.status_code >= 400:
            return {
                "status": "http_error",
                "error": f"http_status_{response.status_code}",
            }

        try:
            page_text = response.content.decode("utf-8", errors="replace")
            parsed_response = self._extract_response_from_page(page_text)
            records = self._extract_response_records(parsed_response)
        except Exception as exc:
            return {
                "status": "parse_error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        return {
            "status": "found" if records else "missing",
            "response": response,
            "parsed_response": parsed_response,
            "records": records,
            "form_data": form_data,
        }

    def _persist_and_materialize_lookup(
        self,
        db: Session,
        *,
        nipt: str,
        response: ResponsePayload,
        parsed_response: Any,
        records: list[dict[str, Any]],
        form_data: dict[str, str],
        lookup_outcome: str,
    ) -> dict[str, Any]:
        external_key = _targeted_external_key(nipt)
        raw_fetch = self.save_raw_fetch(
            db,
            url=response.url,
            content=response.content,
            fetch_kind=TARGETED_NIPT_LOOKUP_FETCH_KIND,
            status_code=response.status_code,
            content_type=response.content_type,
            filename=f"qkb-targeted-nipt-{self._canonicalize_external_key_component(nipt)}.html",
            extra_metadata={
                "collection_mode": TARGETED_NIPT_LOOKUP_MODE,
                "source_type": TARGETED_NIPT_LOOKUP_SOURCE_TYPE,
                "requested_nipt": nipt,
                "lookup_outcome": lookup_outcome,
                "form_data": form_data,
            },
        )
        db.commit()

        company_name = _first_company_name(records)
        structured_record = self.upsert_structured_record(
            db,
            record_type="qkb_search_snapshot",
            external_key=external_key,
            title=f"QKB targeted NIPT lookup {nipt}",
            source_url=response.url,
            content_hash=raw_fetch.content_hash,
            payload={
                "collection_mode": TARGETED_NIPT_LOOKUP_MODE,
                "source_type": TARGETED_NIPT_LOOKUP_SOURCE_TYPE,
                "nipt": nipt,
                "data_nga": None,
                "data_ne": None,
                "raw_fetch_id": raw_fetch.id,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "lookup_outcome": lookup_outcome,
                "response": parsed_response,
            },
            published_at=utc_now_naive(),
            company_name=company_name,
            external_id=nipt,
        )
        db.commit()

        normalized_rows = build_normalized_qkb_search_rows(structured_record)
        for normalized_row in normalized_rows:
            normalized_row.raw_fetch_id = raw_fetch.id
            if normalized_row.source_url is None:
                normalized_row.source_url = response.url

        db.execute(
            delete(NormalizedQkbSearchRow).where(
                NormalizedQkbSearchRow.structured_record_id == structured_record.id
            )
        )
        db.add_all(normalized_rows)
        db.commit()
        return {
            "raw_fetch_id": raw_fetch.id,
            "structured_record_id": structured_record.id,
            "external_key": external_key,
            "rows_materialized": len(normalized_rows),
        }


def _existing_qkb_business_nipts(db: Session, candidate_nipts: Iterable[str]) -> set[str]:
    existing: set[str] = set()
    values = list(candidate_nipts)
    for start in range(0, len(values), _EXISTING_NIPT_QUERY_CHUNK_SIZE):
        chunk = values[start : start + _EXISTING_NIPT_QUERY_CHUNK_SIZE]
        if not chunk:
            continue
        statement = select(NormalizedQkbSearchRow.business_nipt).where(
            func.upper(NormalizedQkbSearchRow.business_nipt).in_(chunk)
        )
        existing.update(
            normalized
            for value in db.scalars(statement)
            if (normalized := normalize_qkb_lookup_nipt(value)) is not None
        )
    return existing


def _missing_fetch_result(*, response: ResponsePayload, form_data: dict[str, str]) -> dict[str, Any]:
    return {
        "status": "missing",
        "response": response,
        "parsed_response": [],
        "records": [],
        "form_data": form_data,
    }


def _http_error_fetch_result(exc: httpx.HTTPError) -> dict[str, Any]:
    status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    error = f"http_status_{status_code}" if status_code is not None else f"{type(exc).__name__}: {exc}"
    return {"status": "http_error", "error": error}


def _response_payload_from_http_error(exc: httpx.HTTPStatusError) -> ResponsePayload:
    response = exc.response
    return ResponsePayload(
        url=str(response.url),
        status_code=response.status_code,
        content_type=response.headers.get("content-type"),
        content=response.content,
        text=response.text,
        cookies=response.cookies,
    )


def _dedupe_nipts(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = normalize_qkb_lookup_nipt(value)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _targeted_external_key(nipt: str) -> str:
    return f"targeted_nipt:{nipt}|none|none"


def _first_company_name(records: list[dict[str, Any]]) -> str | None:
    if not records:
        return None
    value = records[0].get("emriISubjektit")
    return str(value).strip() if value is not None and str(value).strip() else None


def _error_summary(nipt: str | None, stage: str, error: str) -> dict[str, str | None]:
    return {"nipt": nipt, "stage": stage, "error": error}


def _validate_options(*, limit: int, offset: int, delay_seconds: float) -> None:
    if limit < 1:
        raise ValueError("limit must be positive")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")


def _elapsed_seconds(started_at: float) -> float:
    return round(time.monotonic() - started_at, 3)
