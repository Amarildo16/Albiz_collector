from __future__ import annotations

import codecs
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import QkbSearchRun
from ..utils.http import HttpClient, ResponsePayload
from ..utils.time import utc_now_naive
from .base import CollectorBase


RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_INTERRUPTED = "interrupted"
UNFINISHED_RUN_STATUSES = (
    RUN_STATUS_RUNNING,
    RUN_STATUS_FAILED,
    RUN_STATUS_INTERRUPTED,
)
RUN_MODE_DAILY_RANGE = "daily_range"
RUN_START_BEHAVIOR_NEW = "starting_new"
RUN_START_BEHAVIOR_RESUMED = "resuming_existing"
RUN_START_BEHAVIOR_RESTARTED = "restarting_from_scratch"


@dataclass(frozen=True)
class _DailyRunStart:
    run_id: int
    start_behavior: str
    resume_from_date: date
    days_previously_completed_before_run: int


class QkbSearchCollector(CollectorBase):
    source_name = "qkb_search"
    DAILY_RESULT_LIMIT = 50

    @staticmethod
    def _format_form_date(value: date | None) -> str:
        if value is None:
            return ""
        return value.strftime("%d/%m/%Y")

    def collect(
        self,
        db: Session,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
        restart: bool = False,
    ) -> dict[str, Any]:
        if data_nga is not None and data_ne is not None and data_nga > data_ne:
            raise ValueError("data_nga must be on or before data_ne")

        if restart and not self._should_chunk_daily(nipt=nipt, data_nga=data_nga, data_ne=data_ne):
            raise ValueError("restart is only supported for qkb_search date-range runs without nipt")

        requested_range_days = self._requested_range_days(data_nga, data_ne)

        if self._should_chunk_daily(nipt=nipt, data_nga=data_nga, data_ne=data_ne):
            assert data_nga is not None
            assert data_ne is not None
            return self._collect_daily_range(
                db,
                requested_data_nga=data_nga,
                requested_data_ne=data_ne,
                requested_range_days=requested_range_days,
                restart=restart,
            )

        with self._http_client() as http:
            session_cookies = self._establish_search_session(http)
            single_result = self._collect_single_window(
                db,
                http,
                session_cookies=session_cookies,
                nipt=nipt,
                data_nga=data_nga,
                data_ne=data_ne,
            )

        single_day_search = (
            data_nga is not None and data_ne is not None and data_nga == data_ne
        )
        potentially_truncated_days = (
            [data_nga.isoformat()]
            if single_day_search and single_result["potentially_truncated"]
            else []
        )

        return {
            **single_result,
            "search_mode": "single",
            "date_chunking_applied": False,
            "requested_data_nga": data_nga.isoformat() if data_nga else None,
            "requested_data_ne": data_ne.isoformat() if data_ne else None,
            "requested_range_days": requested_range_days,
            "search_requests_executed": 1,
            "total_days_searched": 0,
            "successful_day_searches": 0,
            "failed_day_searches": 0,
            "days_returning_exactly_50_results": len(potentially_truncated_days),
            "potentially_truncated_days": potentially_truncated_days,
            "total_raw_rows_found": single_result["records_found"],
            "total_unique_persisted_snapshots": 1,
            "unique_structured_record_ids": [single_result["structured_record_id"]],
            "unique_external_keys": [single_result["external_key"]],
            "per_day_summaries": [],
        }

    def _collect_daily_range(
        self,
        db: Session,
        *,
        requested_data_nga: date,
        requested_data_ne: date,
        requested_range_days: int,
        restart: bool,
    ) -> dict[str, Any]:
        run_start = self._start_or_resume_daily_run(
            db,
            requested_data_nga=requested_data_nga,
            requested_data_ne=requested_data_ne,
            restart=restart,
        )

        per_day_summaries: list[dict[str, Any]] = []
        unique_structured_record_ids: set[int] = set()
        unique_external_keys: set[str] = set()
        potentially_truncated_days: list[str] = []
        successful_day_searches = 0
        failed_day_searches = 0
        total_raw_rows_found = 0

        try:
            with self._http_client() as http:
                session_cookies = self._establish_search_session(http)
                current = run_start.resume_from_date

                while current <= requested_data_ne:
                    try:
                        result = self._collect_single_window(
                            db,
                            http,
                            session_cookies=session_cookies,
                            nipt=None,
                            data_nga=current,
                            data_ne=current,
                        )
                    except Exception as exc:
                        db.rollback()
                        run = self._get_run(db, run_start.run_id)
                        self._mark_run_failed(run, error=str(exc))
                        db.commit()
                        failed_day_searches += 1
                        per_day_summaries.append(
                            {
                                "day": current.isoformat(),
                                "data_nga": current.isoformat(),
                                "data_ne": current.isoformat(),
                                "status": "failed",
                                "error": str(exc),
                            }
                        )
                        return self._build_daily_run_summary(
                            run=run,
                            run_start=run_start,
                            requested_data_nga=requested_data_nga,
                            requested_data_ne=requested_data_ne,
                            requested_range_days=requested_range_days,
                            successful_day_searches=successful_day_searches,
                            failed_day_searches=failed_day_searches,
                            total_raw_rows_found=total_raw_rows_found,
                            unique_structured_record_ids=unique_structured_record_ids,
                            unique_external_keys=unique_external_keys,
                            potentially_truncated_days=potentially_truncated_days,
                            per_day_summaries=per_day_summaries,
                        )

                    successful_day_searches += 1
                    total_raw_rows_found += result["records_found"]
                    unique_structured_record_ids.add(result["structured_record_id"])
                    unique_external_keys.add(result["external_key"])
                    if result["potentially_truncated"]:
                        potentially_truncated_days.append(current.isoformat())

                    per_day_summaries.append(
                        {
                            "day": current.isoformat(),
                            "status": "ok",
                            **result,
                        }
                    )

                    run = self._get_run(db, run_start.run_id)
                    next_date = current + timedelta(days=1)
                    if next_date > requested_data_ne:
                        self._mark_run_completed(run)
                    else:
                        self._advance_run_progress(run, next_date=next_date)
                    db.commit()
                    current = next_date
        except Exception as exc:
            db.rollback()
            run = self._get_run(db, run_start.run_id)
            self._mark_run_failed(run, error=str(exc))
            db.commit()
            failed_day_searches += 1
            per_day_summaries.append(
                {
                    "day": run.current_date.isoformat() if run.current_date else None,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            return self._build_daily_run_summary(
                run=run,
                run_start=run_start,
                requested_data_nga=requested_data_nga,
                requested_data_ne=requested_data_ne,
                requested_range_days=requested_range_days,
                successful_day_searches=successful_day_searches,
                failed_day_searches=failed_day_searches,
                total_raw_rows_found=total_raw_rows_found,
                unique_structured_record_ids=unique_structured_record_ids,
                unique_external_keys=unique_external_keys,
                potentially_truncated_days=potentially_truncated_days,
                per_day_summaries=per_day_summaries,
            )

        run = self._get_run(db, run_start.run_id)
        return self._build_daily_run_summary(
            run=run,
            run_start=run_start,
            requested_data_nga=requested_data_nga,
            requested_data_ne=requested_data_ne,
            requested_range_days=requested_range_days,
            successful_day_searches=successful_day_searches,
            failed_day_searches=failed_day_searches,
            total_raw_rows_found=total_raw_rows_found,
            unique_structured_record_ids=unique_structured_record_ids,
            unique_external_keys=unique_external_keys,
            potentially_truncated_days=potentially_truncated_days,
            per_day_summaries=per_day_summaries,
        )

    def _build_daily_run_summary(
        self,
        *,
        run: QkbSearchRun,
        run_start: _DailyRunStart,
        requested_data_nga: date,
        requested_data_ne: date,
        requested_range_days: int,
        successful_day_searches: int,
        failed_day_searches: int,
        total_raw_rows_found: int,
        unique_structured_record_ids: set[int],
        unique_external_keys: set[str],
        potentially_truncated_days: list[str],
        per_day_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        days_completed_total = run_start.days_previously_completed_before_run + successful_day_searches
        if run.status == RUN_STATUS_COMPLETED:
            days_completed_total = requested_range_days

        days_remaining_after_run = max(0, requested_range_days - days_completed_total)

        return {
            "source_name": self.source_name,
            "mode": "http",
            "search_mode": RUN_MODE_DAILY_RANGE,
            "date_chunking_applied": True,
            "nipt": None,
            "data_nga": requested_data_nga.isoformat(),
            "data_ne": requested_data_ne.isoformat(),
            "requested_data_nga": requested_data_nga.isoformat(),
            "requested_data_ne": requested_data_ne.isoformat(),
            "requested_range_days": requested_range_days,
            "run_id": run.id,
            "run_status": run.status,
            "run_start_behavior": run_start.start_behavior,
            "resume_from_date": run_start.resume_from_date.isoformat(),
            "run_current_date": run.current_date.isoformat() if run.current_date else None,
            "started_at": run.started_at,
            "updated_at": run.updated_at,
            "completed_at": run.completed_at,
            "last_error": run.last_error,
            "search_requests_executed": successful_day_searches + failed_day_searches,
            "total_days_searched": successful_day_searches + failed_day_searches,
            "successful_day_searches": successful_day_searches,
            "failed_day_searches": failed_day_searches,
            "days_previously_completed_before_run": run_start.days_previously_completed_before_run,
            "days_completed_total": days_completed_total,
            "days_remaining_after_run": days_remaining_after_run,
            "days_returning_exactly_50_results": len(potentially_truncated_days),
            "potentially_truncated_days": potentially_truncated_days,
            "total_raw_rows_found": total_raw_rows_found,
            "records_found": total_raw_rows_found,
            "total_unique_persisted_snapshots": len(unique_structured_record_ids),
            "unique_structured_record_ids": sorted(unique_structured_record_ids),
            "unique_external_keys": sorted(unique_external_keys),
            "per_day_summaries": per_day_summaries,
        }

    def _collect_single_window(
        self,
        db: Session,
        http: HttpClient,
        *,
        session_cookies: Any,
        nipt: str | None,
        data_nga: date | None,
        data_ne: date | None,
    ) -> dict[str, Any]:
        form_data = self._build_form_data(nipt=nipt, data_nga=data_nga, data_ne=data_ne)
        response = self._execute_search_request(http, session_cookies=session_cookies, form_data=form_data)

        raw_row = self.save_raw_fetch(
            db,
            url=response.url,
            content=response.content,
            fetch_kind="search_results_page",
            status_code=response.status_code,
            content_type=response.content_type,
            filename=self._build_filename(nipt=nipt, data_nga=data_nga, data_ne=data_ne),
            extra_metadata={
                "nipt": nipt,
                "data_nga": data_nga.isoformat() if data_nga else None,
                "data_ne": data_ne.isoformat() if data_ne else None,
                "form_data": form_data,
                "mode": "http",
            },
        )
        db.commit()

        page_text = response.content.decode("utf-8", errors="replace")
        try:
            parsed_response = self._extract_response_from_page(page_text)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse QKB search response from saved raw fetch {raw_row.id}"
            ) from exc

        external_key = self._build_external_key(nipt=nipt, data_nga=data_nga, data_ne=data_ne)
        structured_row = self.upsert_structured_record(
            db,
            record_type="qkb_search_snapshot",
            external_key=external_key,
            title=f"QKB search snapshot {external_key}",
            source_url=response.url,
            content_hash=raw_row.content_hash,
            payload={
                "nipt": nipt,
                "data_nga": data_nga.isoformat() if data_nga else None,
                "data_ne": data_ne.isoformat() if data_ne else None,
                "raw_fetch_id": raw_row.id,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "response": parsed_response,
            },
            published_at=utc_now_naive(),
        )
        db.commit()

        records_found = self._count_records(parsed_response)
        one_day_search = (
            data_nga is not None and data_ne is not None and data_nga == data_ne
        )

        return {
            "source_name": self.source_name,
            "nipt": nipt,
            "data_nga": data_nga.isoformat() if data_nga else None,
            "data_ne": data_ne.isoformat() if data_ne else None,
            "raw_fetch_id": raw_row.id,
            "structured_record_id": structured_row.id,
            "external_key": external_key,
            "status_code": response.status_code,
            "content_type": response.content_type,
            "url": response.url,
            "mode": "http",
            "records_found": records_found,
            "potentially_truncated": one_day_search and records_found == self.DAILY_RESULT_LIMIT,
        }

    def _build_form_data(
        self,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
    ) -> dict[str, str]:
        return {
            "orderColumn": "0",
            "orderDir": "asc",
            "nipt": nipt or "",
            "emriISubjektit": "",
            "emriTregtar": "",
            "formeLigjore": "",
            "pronesia": "",
            "dataNga": self._format_form_date(data_nga),
            "dataNe": self._format_form_date(data_ne),
            "numriId": "",
            "administrator": "",
            "aksionerOrtak": "",
            "sektoriIVeprimtarise": "",
            "qarku": "",
            "qyteti": "",
            "adresa": "",
        }

    def _build_headers(self) -> dict[str, str]:
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://format.qkb.gov.al",
            "Referer": settings.qkb_search_url,
        }

    def _build_filename(
        self,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
    ) -> str:
        nipt_part = nipt or "all"
        from_part = data_nga.isoformat() if data_nga else "none"
        to_part = data_ne.isoformat() if data_ne else "none"
        return f"qkb-search-{nipt_part}-{from_part}-{to_part}.html"

    def _build_external_key(
        self,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
    ) -> str:
        return "|".join(
            [
                nipt or "all",
                data_nga.isoformat() if data_nga else "none",
                data_ne.isoformat() if data_ne else "none",
            ]
        )

    def _count_records(self, parsed_response: Any) -> int:
        if isinstance(parsed_response, list):
            return len(parsed_response)

        if isinstance(parsed_response, dict):
            data = parsed_response.get("data")
            if isinstance(data, list):
                return len(data)

        return 0

    def _extract_response_from_page(self, page_content: str) -> Any:
        parsed_patterns = [
            r'response\s*=\s*JSON\.parse\s*\(\s*"(?P<payload>(?:\\.|[^"\\])*)"\s*\)',
            r"response\s*=\s*JSON\.parse\s*\(\s*'(?P<payload>(?:\\.|[^'\\])*)'\s*\)",
        ]

        for pattern in parsed_patterns:
            match = re.search(pattern, page_content, re.DOTALL)
            if match:
                escaped_payload = match.group("payload")
                decoded_payload = self._decode_json_parse_payload(escaped_payload)
                return json.loads(decoded_payload)

        direct_match = re.search(
            r"response\s*=\s*(?P<payload>\{[\s\S]*?\}|\[[\s\S]*?\])\s*;",
            page_content,
            re.DOTALL,
        )
        if direct_match:
            return json.loads(direct_match.group("payload"))

        raise ValueError("Could not find JavaScript response variable in QKB search HTML")

    @staticmethod
    def _decode_json_parse_payload(payload: str) -> str:
        try:
            return json.loads(f'"{payload}"')
        except json.JSONDecodeError:
            return codecs.decode(payload, "unicode_escape")

    @staticmethod
    def _should_chunk_daily(
        *,
        nipt: str | None,
        data_nga: date | None,
        data_ne: date | None,
    ) -> bool:
        return nipt is None and data_nga is not None and data_ne is not None

    @staticmethod
    def _requested_range_days(data_nga: date | None, data_ne: date | None) -> int:
        if data_nga is None or data_ne is None:
            return 0
        return (data_ne - data_nga).days + 1

    def _start_or_resume_daily_run(
        self,
        db: Session,
        *,
        requested_data_nga: date,
        requested_data_ne: date,
        restart: bool,
    ) -> _DailyRunStart:
        existing_runs = db.scalars(
            select(QkbSearchRun)
            .where(
                QkbSearchRun.collector_name == self.source_name,
                QkbSearchRun.mode == RUN_MODE_DAILY_RANGE,
                QkbSearchRun.date_from == requested_data_nga,
                QkbSearchRun.date_to == requested_data_ne,
                QkbSearchRun.status.in_(UNFINISHED_RUN_STATUSES),
            )
            .order_by(QkbSearchRun.id.desc())
        ).all()

        now = utc_now_naive()

        if restart:
            self._interrupt_runs(
                existing_runs,
                reason="Interrupted by operator restart.",
                interrupted_at=now,
            )
            run = QkbSearchRun(
                collector_name=self.source_name,
                mode=RUN_MODE_DAILY_RANGE,
                date_from=requested_data_nga,
                date_to=requested_data_ne,
                current_date=requested_data_nga,
                status=RUN_STATUS_RUNNING,
                started_at=now,
                updated_at=now,
                completed_at=None,
                last_error=None,
            )
            db.add(run)
            db.commit()
            return _DailyRunStart(
                run_id=run.id,
                start_behavior=RUN_START_BEHAVIOR_RESTARTED,
                resume_from_date=requested_data_nga,
                days_previously_completed_before_run=0,
            )

        if existing_runs:
            active_run = existing_runs[0]
            if len(existing_runs) > 1:
                self._interrupt_runs(
                    existing_runs[1:],
                    reason=f"Superseded by resumable run {active_run.id}.",
                    interrupted_at=now,
                )

            resume_from_date = active_run.current_date or requested_data_nga
            if resume_from_date < requested_data_nga or resume_from_date > requested_data_ne:
                resume_from_date = requested_data_nga
                active_run.current_date = requested_data_nga

            active_run.status = RUN_STATUS_RUNNING
            active_run.updated_at = now
            db.commit()
            return _DailyRunStart(
                run_id=active_run.id,
                start_behavior=RUN_START_BEHAVIOR_RESUMED,
                resume_from_date=resume_from_date,
                days_previously_completed_before_run=max(
                    0,
                    (resume_from_date - requested_data_nga).days,
                ),
            )

        run = QkbSearchRun(
            collector_name=self.source_name,
            mode=RUN_MODE_DAILY_RANGE,
            date_from=requested_data_nga,
            date_to=requested_data_ne,
            current_date=requested_data_nga,
            status=RUN_STATUS_RUNNING,
            started_at=now,
            updated_at=now,
            completed_at=None,
            last_error=None,
        )
        db.add(run)
        db.commit()
        return _DailyRunStart(
            run_id=run.id,
            start_behavior=RUN_START_BEHAVIOR_NEW,
            resume_from_date=requested_data_nga,
            days_previously_completed_before_run=0,
        )

    @staticmethod
    def _interrupt_runs(
        runs: list[QkbSearchRun],
        *,
        reason: str,
        interrupted_at,
    ) -> None:
        for run in runs:
            run.status = RUN_STATUS_INTERRUPTED
            run.updated_at = interrupted_at
            run.last_error = reason

    @staticmethod
    def _advance_run_progress(run: QkbSearchRun, *, next_date: date) -> None:
        run.current_date = next_date
        run.status = RUN_STATUS_RUNNING
        run.updated_at = utc_now_naive()
        run.last_error = None

    @staticmethod
    def _mark_run_failed(run: QkbSearchRun, *, error: str) -> None:
        run.status = RUN_STATUS_FAILED
        run.updated_at = utc_now_naive()
        run.last_error = error

    @staticmethod
    def _mark_run_completed(run: QkbSearchRun) -> None:
        completed_at = utc_now_naive()
        run.current_date = None
        run.status = RUN_STATUS_COMPLETED
        run.updated_at = completed_at
        run.completed_at = completed_at
        run.last_error = None

    @staticmethod
    def _get_run(db: Session, run_id: int) -> QkbSearchRun:
        run = db.get(QkbSearchRun, run_id)
        if run is None:
            raise RuntimeError(f"QKB search run {run_id} no longer exists")
        return run

    def _http_client(self) -> HttpClient:
        return HttpClient()

    def _establish_search_session(self, http: HttpClient) -> Any:
        initial_response = http.get(settings.qkb_search_url)
        return initial_response.cookies

    def _execute_search_request(
        self,
        http: HttpClient,
        *,
        session_cookies: Any,
        form_data: dict[str, str],
    ) -> ResponsePayload:
        return http.post(
            settings.qkb_search_url,
            data=form_data,
            headers=self._build_headers(),
            cookies=session_cookies,
        )
