from __future__ import annotations

import codecs
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import QkbSearchRun
from ..qkb_legal_forms import (
    QKB_SHA_LEGAL_FORM_VALUE,
    QKB_SHPK_LEGAL_FORM_VALUE,
    canonicalize_qkb_legal_form,
    resolve_qkb_legal_form_filter,
)
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
RUN_MODE_DAILY_LEGAL_FORM = "daily_legal_form"
RUN_START_BEHAVIOR_NEW = "starting_new"
RUN_START_BEHAVIOR_RESUMED = "resuming_existing"
RUN_START_BEHAVIOR_RESTARTED = "restarting_from_scratch"
QKB_LEGAL_FORM_FILTER_VALUES = (
    "Person Fizik",
    QKB_SHPK_LEGAL_FORM_VALUE,
    QKB_SHA_LEGAL_FORM_VALUE,
    "Dege e Shoqerise se huaj",
    "Shoqeri Kolektive",
    "Shoqeri e Thjeshte",
    "Shoqeri Komandite",
    "Shoqeri Kursim Krediti",
    "Shoqeri Bashkeveprim Reciprok",
    "Shoqeri e Bashkepunimit Bujqesor",
    "Shoqeri Aksionare me Oferte Publike",
)


@dataclass(frozen=True)
class _DailyRunStart:
    run_id: int
    start_behavior: str
    resume_from_date: date
    days_previously_completed_before_run: int


@dataclass(frozen=True)
class _ParsedSearchResult:
    response: ResponsePayload
    parsed_response: Any
    records: list[dict[str, Any]]
    records_found: int
    business_nipts: list[str]


class _SelectOptionParser(HTMLParser):
    def __init__(self, field_names: tuple[str, ...]) -> None:
        super().__init__(convert_charrefs=True)
        self._field_names = set(field_names)
        self._current_select_name: str | None = None
        self._current_option_value: str | None = None
        self._current_option_label_parts: list[str] = []
        self.options_by_field: dict[str, list[dict[str, str]]] = {
            field_name: [] for field_name in field_names
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "select":
            select_name = attr_map.get("name") or attr_map.get("id")
            self._current_select_name = select_name if select_name in self._field_names else None
            return

        if tag == "option" and self._current_select_name is not None:
            self._current_option_value = attr_map.get("value") or ""
            self._current_option_label_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_select_name is not None and self._current_option_value is not None:
            self._current_option_label_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._current_select_name is not None and self._current_option_value is not None:
            value = self._current_option_value.strip()
            label = " ".join("".join(self._current_option_label_parts).split())
            if value:
                existing_values = {
                    option["value"] for option in self.options_by_field[self._current_select_name]
                }
                if value not in existing_values:
                    self.options_by_field[self._current_select_name].append(
                        {"value": value, "label": label or value}
                    )
            self._current_option_value = None
            self._current_option_label_parts = []
            return

        if tag == "select":
            self._current_select_name = None
            self._current_option_value = None
            self._current_option_label_parts = []


class QkbSearchCollector(CollectorBase):
    source_name = "qkb_search"
    DAILY_RESULT_LIMIT = 50
    SECONDARY_CHUNK_FIELD_QARKU = "qarku"
    SECONDARY_CHUNK_FIELD_PREFERENCES = ("qarku", "qyteti")

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
        forme_ligjore: str | None = None,
        restart: bool = False,
    ) -> dict[str, Any]:
        if data_nga is not None and data_ne is not None and data_nga > data_ne:
            raise ValueError("data_nga must be on or before data_ne")

        legal_form_filter = resolve_qkb_legal_form_filter(forme_ligjore)
        canonical_legal_form_filter = canonicalize_qkb_legal_form(legal_form_filter)
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
                run_mode=self._run_mode_for_legal_form(canonical_legal_form_filter),
                legal_form_filter=legal_form_filter,
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
                legal_form_filter=legal_form_filter,
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

    def probe_legal_form_chunks(
        self,
        *,
        probe_date: date,
        legal_form_filters: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        filters = legal_form_filters or QKB_LEGAL_FORM_FILTER_VALUES
        per_legal_form_results: list[dict[str, Any]] = []

        with self._http_client() as http:
            session_cookies = self._establish_search_session(http)
            for legal_form_filter in filters:
                per_legal_form_results.append(
                    self._probe_single_legal_form_chunk(
                        http,
                        session_cookies=session_cookies,
                        probe_date=probe_date,
                        legal_form_filter=legal_form_filter,
                    )
                )

        total_raw_rows_found = sum(
            result["records_found"]
            for result in per_legal_form_results
            if isinstance(result["records_found"], int)
        )
        potentially_truncated_results = [
            result
            for result in per_legal_form_results
            if result["potentially_truncated"]
        ]
        failed_results = [
            result
            for result in per_legal_form_results
            if result["status"] != "ok"
        ]

        return {
            "source_name": self.source_name,
            "mode": "http",
            "probe_type": "qkb_legal_form_chunk_probe",
            "persistence": "none",
            "probe_date": probe_date.isoformat(),
            "total_requests_executed": len(per_legal_form_results),
            "successful_requests": len(per_legal_form_results) - len(failed_results),
            "failed_requests": len(failed_results),
            "total_raw_rows_found": total_raw_rows_found,
            "legal_forms_returning_exactly_50_results": len(potentially_truncated_results),
            "potentially_truncated_legal_forms": [
                result["legal_form_filter"]
                for result in potentially_truncated_results
            ],
            "legal_form_chunking_appears_sufficient": not failed_results and not potentially_truncated_results,
            "results": per_legal_form_results,
        }

    def probe_secondary_chunks(
        self,
        *,
        probe_date: date,
        forme_ligjore: str,
        secondary_field_preferences: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        legal_form_filter = resolve_qkb_legal_form_filter(forme_ligjore)
        canonical_legal_form = canonicalize_qkb_legal_form(legal_form_filter)
        field_preferences = secondary_field_preferences or self.SECONDARY_CHUNK_FIELD_PREFERENCES

        with self._http_client() as http:
            initial_response = http.get(settings.qkb_search_url)
            session_cookies = initial_response.cookies
            search_form_text = initial_response.text or initial_response.content.decode(
                "utf-8", errors="replace"
            )
            secondary_filter_candidates = self._extract_secondary_filter_candidates(
                search_form_text,
                field_preferences=field_preferences,
            )
            selected_filter = secondary_filter_candidates[0] if secondary_filter_candidates else None

            baseline_result = self._probe_single_secondary_chunk(
                http,
                session_cookies=session_cookies,
                probe_date=probe_date,
                legal_form_filter=legal_form_filter,
                secondary_filter_field_name=None,
                secondary_filter_value=None,
                secondary_filter_label=None,
            )

            per_filter_results: list[dict[str, Any]] = []
            if selected_filter is not None:
                for option in selected_filter["options"]:
                    per_filter_results.append(
                        self._probe_single_secondary_chunk(
                            http,
                            session_cookies=session_cookies,
                            probe_date=probe_date,
                            legal_form_filter=legal_form_filter,
                            secondary_filter_field_name=selected_filter["field_name"],
                            secondary_filter_value=option["value"],
                            secondary_filter_label=option["label"],
                        )
                    )

        total_rows_across_chunks = sum(
            result["records_found"]
            for result in per_filter_results
            if isinstance(result["records_found"], int)
        )
        potentially_truncated_results = [
            result for result in per_filter_results if result["potentially_truncated"]
        ]
        failed_results = [
            result for result in per_filter_results if result["status"] != "ok"
        ]
        unique_nipts = self._dedupe_preserving_order(
            nipt
            for result in per_filter_results
            for nipt in result.get("business_nipts", [])
        )

        return {
            "source_name": self.source_name,
            "mode": "http",
            "probe_type": "qkb_secondary_chunk_probe",
            "persistence": "none",
            "date": probe_date.isoformat(),
            "requested_legal_form": forme_ligjore,
            "resolved_legal_form_filter": legal_form_filter,
            "canonical_legal_form_filter": canonical_legal_form,
            "baseline_records_found": baseline_result["records_found"],
            "baseline_potentially_truncated": baseline_result["potentially_truncated"],
            "baseline_result": baseline_result,
            "discovered_secondary_filter_fields": [
                {
                    "field_name": candidate["field_name"],
                    "option_count": len(candidate["options"]),
                }
                for candidate in secondary_filter_candidates
            ],
            "candidate_secondary_filter_field_name": (
                selected_filter["field_name"] if selected_filter is not None else None
            ),
            "candidate_secondary_filter_values_tested": len(per_filter_results),
            "total_requests_executed": 1 + len(per_filter_results),
            "successful_requests": 1 + len(per_filter_results) - len(failed_results),
            "failed_requests": len(failed_results),
            "total_rows_across_chunks_before_dedupe": total_rows_across_chunks,
            "unique_business_nipt_count_across_chunks": len(unique_nipts),
            "unique_business_nipts_across_chunks": unique_nipts,
            "secondary_chunks_returning_exactly_50_results": len(potentially_truncated_results),
            "potentially_truncated_secondary_filter_values": [
                result["secondary_filter_value"] for result in potentially_truncated_results
            ],
            "secondary_chunking_appears_sufficient": (
                selected_filter is not None
                and not failed_results
                and not potentially_truncated_results
            ),
            "results": per_filter_results,
        }

    def _probe_single_legal_form_chunk(
        self,
        http: HttpClient,
        *,
        session_cookies: Any,
        probe_date: date,
        legal_form_filter: str,
    ) -> dict[str, Any]:
        form_data = self._build_form_data(
            data_nga=probe_date,
            data_ne=probe_date,
            legal_form=legal_form_filter,
        )
        response: ResponsePayload | None = None
        try:
            response = self._execute_search_request(
                http,
                session_cookies=session_cookies,
                form_data=form_data,
            )
            page_text = response.content.decode("utf-8", errors="replace")
            parsed_response = self._extract_response_from_page(page_text)
            records_found = self._count_records(parsed_response)
            return {
                "status": "ok",
                "legal_form_filter": legal_form_filter,
                "canonical_legal_form": canonicalize_qkb_legal_form(legal_form_filter),
                "records_found": records_found,
                "potentially_truncated": records_found == self.DAILY_RESULT_LIMIT,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "url": response.url,
                "error": None,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "legal_form_filter": legal_form_filter,
                "canonical_legal_form": canonicalize_qkb_legal_form(legal_form_filter),
                "records_found": None,
                "potentially_truncated": False,
                "status_code": response.status_code if response is not None else None,
                "content_type": response.content_type if response is not None else None,
                "url": response.url if response is not None else None,
                "error": str(exc),
            }

    def _probe_single_secondary_chunk(
        self,
        http: HttpClient,
        *,
        session_cookies: Any,
        probe_date: date,
        legal_form_filter: str | None,
        secondary_filter_field_name: str | None,
        secondary_filter_value: str | None,
        secondary_filter_label: str | None,
    ) -> dict[str, Any]:
        secondary_filters = (
            {secondary_filter_field_name: secondary_filter_value}
            if secondary_filter_field_name is not None and secondary_filter_value is not None
            else None
        )
        form_data = self._build_form_data(
            data_nga=probe_date,
            data_ne=probe_date,
            legal_form=legal_form_filter,
            secondary_filters=secondary_filters,
        )
        response: ResponsePayload | None = None
        try:
            response = self._execute_search_request(
                http,
                session_cookies=session_cookies,
                form_data=form_data,
            )
            page_text = response.content.decode("utf-8", errors="replace")
            parsed_response = self._extract_response_from_page(page_text)
            records = self._extract_response_records(parsed_response)
            business_nipts = self._extract_business_nipts(records)
            records_found = len(records)
            return {
                "status": "ok",
                "date": probe_date.isoformat(),
                "legal_form_filter": legal_form_filter,
                "canonical_legal_form": canonicalize_qkb_legal_form(legal_form_filter),
                "secondary_filter_field_name": secondary_filter_field_name,
                "secondary_filter_value": secondary_filter_value,
                "secondary_filter_label": secondary_filter_label,
                "records_found": records_found,
                "potentially_truncated": records_found == self.DAILY_RESULT_LIMIT,
                "business_nipts": business_nipts,
                "unique_business_nipt_count": len(business_nipts),
                "status_code": response.status_code,
                "content_type": response.content_type,
                "url": response.url,
                "error": None,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "date": probe_date.isoformat(),
                "legal_form_filter": legal_form_filter,
                "canonical_legal_form": canonicalize_qkb_legal_form(legal_form_filter),
                "secondary_filter_field_name": secondary_filter_field_name,
                "secondary_filter_value": secondary_filter_value,
                "secondary_filter_label": secondary_filter_label,
                "records_found": None,
                "potentially_truncated": False,
                "business_nipts": [],
                "unique_business_nipt_count": 0,
                "status_code": response.status_code if response is not None else None,
                "content_type": response.content_type if response is not None else None,
                "url": response.url if response is not None else None,
                "error": str(exc),
            }

    def _collect_daily_range(
        self,
        db: Session,
        *,
        requested_data_nga: date,
        requested_data_ne: date,
        requested_range_days: int,
        restart: bool,
        run_mode: str = RUN_MODE_DAILY_RANGE,
        legal_form_filter: str | None = None,
    ) -> dict[str, Any]:
        run_start = self._start_or_resume_daily_run(
            db,
            requested_data_nga=requested_data_nga,
            requested_data_ne=requested_data_ne,
            restart=restart,
            run_mode=run_mode,
        )

        per_day_summaries: list[dict[str, Any]] = []
        unique_structured_record_ids: set[int] = set()
        unique_external_keys: set[str] = set()
        potentially_truncated_days: list[str] = []
        secondary_chunking_applied_days: list[str] = []
        secondary_potentially_truncated_days: list[str] = []
        secondary_unique_nipts: list[str] = []
        secondary_total_rows_before_dedupe = 0
        secondary_chunks_returning_exactly_50_results = 0
        successful_day_searches = 0
        failed_day_searches = 0
        search_requests_executed = 0
        total_raw_rows_found = 0

        try:
            with self._http_client() as http:
                initial_response = self._load_search_form(http)
                session_cookies = initial_response.cookies
                search_form_text = initial_response.text or initial_response.content.decode(
                    "utf-8", errors="replace"
                )
                qarku_options = self._extract_qarku_filter_options(search_form_text) if legal_form_filter else []
                current = run_start.resume_from_date

                while current <= requested_data_ne:
                    try:
                        if legal_form_filter:
                            result = self._collect_legal_form_day_with_qarku_fallback(
                                db,
                                http,
                                session_cookies=session_cookies,
                                data_nga=current,
                                data_ne=current,
                                legal_form_filter=legal_form_filter,
                                qarku_options=qarku_options,
                            )
                        else:
                            result = self._collect_single_window(
                                db,
                                http,
                                session_cookies=session_cookies,
                                nipt=None,
                                data_nga=current,
                                data_ne=current,
                                legal_form_filter=None,
                            )
                    except Exception as exc:
                        db.rollback()
                        run = self._get_run(db, run_start.run_id)
                        self._mark_run_failed(run, error=str(exc))
                        db.commit()
                        failed_day_searches += 1
                        search_requests_executed += 1
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
                            run_mode=run_mode,
                            legal_form_filter=legal_form_filter,
                            successful_day_searches=successful_day_searches,
                            failed_day_searches=failed_day_searches,
                            search_requests_executed=search_requests_executed,
                            total_raw_rows_found=total_raw_rows_found,
                            unique_structured_record_ids=unique_structured_record_ids,
                            unique_external_keys=unique_external_keys,
                            potentially_truncated_days=potentially_truncated_days,
                            secondary_chunking_applied_days=secondary_chunking_applied_days,
                            secondary_potentially_truncated_days=secondary_potentially_truncated_days,
                            secondary_total_rows_before_dedupe=secondary_total_rows_before_dedupe,
                            secondary_unique_nipts=secondary_unique_nipts,
                            secondary_chunks_returning_exactly_50_results=secondary_chunks_returning_exactly_50_results,
                            per_day_summaries=per_day_summaries,
                        )

                    successful_day_searches += 1
                    search_requests_executed += result.get("search_requests_executed", 1)
                    total_raw_rows_found += result["records_found"]
                    unique_structured_record_ids.update(result.get("structured_record_ids", []))
                    unique_external_keys.update(result.get("external_keys", []))
                    if result.get("structured_record_id") is not None:
                        unique_structured_record_ids.add(result["structured_record_id"])
                    if result.get("external_key") is not None:
                        unique_external_keys.add(result["external_key"])
                    if result["potentially_truncated"]:
                        potentially_truncated_days.append(current.isoformat())
                    if result.get("secondary_chunking_applied"):
                        secondary_chunking_applied_days.append(current.isoformat())
                        secondary_total_rows_before_dedupe += result.get(
                            "secondary_total_rows_before_dedupe", 0
                        )
                        chunk_limit_hits = result.get(
                            "secondary_chunks_returning_exactly_50_results",
                            0,
                        )
                        secondary_chunks_returning_exactly_50_results += chunk_limit_hits
                        if chunk_limit_hits:
                            secondary_potentially_truncated_days.append(current.isoformat())
                        secondary_unique_nipts = self._dedupe_preserving_order(
                            [*secondary_unique_nipts, *result.get("secondary_unique_nipts", [])]
                        )

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
            search_requests_executed += 1
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
                run_mode=run_mode,
                legal_form_filter=legal_form_filter,
                successful_day_searches=successful_day_searches,
                failed_day_searches=failed_day_searches,
                search_requests_executed=search_requests_executed,
                total_raw_rows_found=total_raw_rows_found,
                unique_structured_record_ids=unique_structured_record_ids,
                unique_external_keys=unique_external_keys,
                potentially_truncated_days=potentially_truncated_days,
                secondary_chunking_applied_days=secondary_chunking_applied_days,
                secondary_potentially_truncated_days=secondary_potentially_truncated_days,
                secondary_total_rows_before_dedupe=secondary_total_rows_before_dedupe,
                secondary_unique_nipts=secondary_unique_nipts,
                secondary_chunks_returning_exactly_50_results=secondary_chunks_returning_exactly_50_results,
                per_day_summaries=per_day_summaries,
            )

        run = self._get_run(db, run_start.run_id)
        return self._build_daily_run_summary(
            run=run,
            run_start=run_start,
            requested_data_nga=requested_data_nga,
            requested_data_ne=requested_data_ne,
            requested_range_days=requested_range_days,
            run_mode=run_mode,
            legal_form_filter=legal_form_filter,
            successful_day_searches=successful_day_searches,
            failed_day_searches=failed_day_searches,
            search_requests_executed=search_requests_executed,
            total_raw_rows_found=total_raw_rows_found,
            unique_structured_record_ids=unique_structured_record_ids,
            unique_external_keys=unique_external_keys,
            potentially_truncated_days=potentially_truncated_days,
            secondary_chunking_applied_days=secondary_chunking_applied_days,
            secondary_potentially_truncated_days=secondary_potentially_truncated_days,
            secondary_total_rows_before_dedupe=secondary_total_rows_before_dedupe,
            secondary_unique_nipts=secondary_unique_nipts,
            secondary_chunks_returning_exactly_50_results=secondary_chunks_returning_exactly_50_results,
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
        run_mode: str,
        legal_form_filter: str | None,
        successful_day_searches: int,
        failed_day_searches: int,
        search_requests_executed: int,
        total_raw_rows_found: int,
        unique_structured_record_ids: set[int],
        unique_external_keys: set[str],
        potentially_truncated_days: list[str],
        secondary_chunking_applied_days: list[str],
        secondary_potentially_truncated_days: list[str],
        secondary_total_rows_before_dedupe: int,
        secondary_unique_nipts: list[str],
        secondary_chunks_returning_exactly_50_results: int,
        per_day_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        days_completed_total = run_start.days_previously_completed_before_run + successful_day_searches
        if run.status == RUN_STATUS_COMPLETED:
            days_completed_total = requested_range_days

        days_remaining_after_run = max(0, requested_range_days - days_completed_total)
        canonical_legal_form = canonicalize_qkb_legal_form(legal_form_filter)

        summary = {
            "source_name": self.source_name,
            "mode": "http",
            "search_mode": run_mode,
            "date_chunking_applied": True,
            "nipt": None,
            "legal_form_filter": legal_form_filter,
            "canonical_legal_form_filter": canonical_legal_form,
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
            "search_requests_executed": search_requests_executed,
            "total_days_searched": successful_day_searches + failed_day_searches,
            "successful_day_searches": successful_day_searches,
            "failed_day_searches": failed_day_searches,
            "days_previously_completed_before_run": run_start.days_previously_completed_before_run,
            "days_completed_total": days_completed_total,
            "days_remaining_after_run": days_remaining_after_run,
            "days_returning_exactly_50_results": len(potentially_truncated_days),
            "potentially_truncated_days": potentially_truncated_days,
            "secondary_chunking_applied_days": secondary_chunking_applied_days,
            "secondary_chunking_field": self.SECONDARY_CHUNK_FIELD_QARKU if secondary_chunking_applied_days else None,
            "secondary_chunked_days_count": len(secondary_chunking_applied_days),
            "secondary_chunks_returning_exactly_50_results": secondary_chunks_returning_exactly_50_results,
            "secondary_potentially_truncated_days": secondary_potentially_truncated_days,
            "secondary_total_rows_before_dedupe": secondary_total_rows_before_dedupe,
            "secondary_unique_nipt_count": len(secondary_unique_nipts),
            "secondary_unique_nipts": secondary_unique_nipts,
            "total_raw_rows_found": total_raw_rows_found,
            "records_found": total_raw_rows_found,
            "total_unique_persisted_snapshots": len(unique_structured_record_ids),
            "unique_structured_record_ids": sorted(unique_structured_record_ids),
            "unique_external_keys": sorted(unique_external_keys),
            "per_day_summaries": per_day_summaries,
        }

        return summary

    def _collect_legal_form_day_with_qarku_fallback(
        self,
        db: Session,
        http: HttpClient,
        *,
        session_cookies: Any,
        data_nga: date,
        data_ne: date,
        legal_form_filter: str,
        qarku_options: list[dict[str, str]],
    ) -> dict[str, Any]:
        baseline_form_data = self._build_form_data(
            data_nga=data_nga,
            data_ne=data_ne,
            legal_form=legal_form_filter,
        )
        baseline_result = self._execute_and_parse_search(
            http,
            session_cookies=session_cookies,
            form_data=baseline_form_data,
        )

        if baseline_result.records_found != self.DAILY_RESULT_LIMIT or not qarku_options:
            persisted_baseline = self._persist_search_result(
                db,
                parsed_result=baseline_result,
                form_data=baseline_form_data,
                nipt=None,
                data_nga=data_nga,
                data_ne=data_ne,
                legal_form_filter=legal_form_filter,
                secondary_filters=None,
                secondary_filter_labels=None,
            )
            return {
                **persisted_baseline,
                "search_requests_executed": 1,
                "secondary_chunking_applied": False,
                "secondary_chunking_field": None,
                "secondary_chunk_summaries": [],
            }

        chunk_summaries: list[dict[str, Any]] = []
        structured_record_ids: list[int] = []
        external_keys: list[str] = []
        raw_fetch_ids: list[int] = []
        total_rows_before_dedupe = 0
        unique_nipts: list[str] = []
        qarku_chunks_returning_limit = 0

        for option in qarku_options:
            qarku_value = option["value"]
            qarku_label = option["label"]
            secondary_filters = {self.SECONDARY_CHUNK_FIELD_QARKU: qarku_value}
            secondary_filter_labels = {self.SECONDARY_CHUNK_FIELD_QARKU: qarku_label}
            form_data = self._build_form_data(
                data_nga=data_nga,
                data_ne=data_ne,
                legal_form=legal_form_filter,
                secondary_filters=secondary_filters,
            )
            chunk_result = self._execute_and_parse_search(
                http,
                session_cookies=session_cookies,
                form_data=form_data,
            )
            persisted_chunk = self._persist_search_result(
                db,
                parsed_result=chunk_result,
                form_data=form_data,
                nipt=None,
                data_nga=data_nga,
                data_ne=data_ne,
                legal_form_filter=legal_form_filter,
                secondary_filters=secondary_filters,
                secondary_filter_labels=secondary_filter_labels,
            )

            total_rows_before_dedupe += persisted_chunk["records_found"]
            unique_nipts = self._dedupe_preserving_order(
                [*unique_nipts, *chunk_result.business_nipts]
            )
            raw_fetch_ids.append(persisted_chunk["raw_fetch_id"])
            structured_record_ids.append(persisted_chunk["structured_record_id"])
            external_keys.append(persisted_chunk["external_key"])
            if persisted_chunk["potentially_truncated"]:
                qarku_chunks_returning_limit += 1

            chunk_summaries.append(
                {
                    **persisted_chunk,
                    "qarku": qarku_value,
                    "qarku_label": qarku_label,
                    "business_nipts": chunk_result.business_nipts,
                    "unique_business_nipt_count": len(chunk_result.business_nipts),
                }
            )

        return {
            "source_name": self.source_name,
            "nipt": None,
            "legal_form_filter": legal_form_filter,
            "canonical_legal_form_filter": canonicalize_qkb_legal_form(legal_form_filter),
            "data_nga": data_nga.isoformat(),
            "data_ne": data_ne.isoformat(),
            "raw_fetch_id": None,
            "raw_fetch_ids": raw_fetch_ids,
            "structured_record_id": None,
            "structured_record_ids": structured_record_ids,
            "external_key": None,
            "external_keys": external_keys,
            "status_code": baseline_result.response.status_code,
            "content_type": baseline_result.response.content_type,
            "url": baseline_result.response.url,
            "mode": "http",
            "records_found": total_rows_before_dedupe,
            "potentially_truncated": qarku_chunks_returning_limit > 0,
            "search_requests_executed": 1 + len(qarku_options),
            "baseline_records_found": baseline_result.records_found,
            "baseline_potentially_truncated": True,
            "baseline_persisted": False,
            "secondary_chunking_applied": True,
            "secondary_chunking_field": self.SECONDARY_CHUNK_FIELD_QARKU,
            "secondary_total_rows_before_dedupe": total_rows_before_dedupe,
            "secondary_unique_nipt_count": len(unique_nipts),
            "secondary_unique_nipts": unique_nipts,
            "secondary_chunks_returning_exactly_50_results": qarku_chunks_returning_limit,
            "secondary_potentially_truncated_filter_values": [
                chunk["qarku"]
                for chunk in chunk_summaries
                if chunk["potentially_truncated"]
            ],
            "secondary_chunk_summaries": chunk_summaries,
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
        legal_form_filter: str | None = None,
        secondary_filters: dict[str, str] | None = None,
        secondary_filter_labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        form_data = self._build_form_data(
            nipt=nipt,
            data_nga=data_nga,
            data_ne=data_ne,
            legal_form=legal_form_filter,
            secondary_filters=secondary_filters,
        )
        parsed_result = self._execute_and_parse_search(
            http,
            session_cookies=session_cookies,
            form_data=form_data,
        )
        return self._persist_search_result(
            db,
            parsed_result=parsed_result,
            form_data=form_data,
            nipt=nipt,
            data_nga=data_nga,
            data_ne=data_ne,
            legal_form_filter=legal_form_filter,
            secondary_filters=secondary_filters,
            secondary_filter_labels=secondary_filter_labels,
        )

    def _persist_search_result(
        self,
        db: Session,
        *,
        parsed_result: _ParsedSearchResult,
        form_data: dict[str, str],
        nipt: str | None,
        data_nga: date | None,
        data_ne: date | None,
        legal_form_filter: str | None = None,
        secondary_filters: dict[str, str] | None = None,
        secondary_filter_labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        canonical_legal_form = canonicalize_qkb_legal_form(legal_form_filter)
        response = parsed_result.response
        raw_row = self.save_raw_fetch(
            db,
            url=response.url,
            content=response.content,
            fetch_kind="search_results_page",
            status_code=response.status_code,
            content_type=response.content_type,
            filename=self._build_filename(
                nipt=nipt,
                data_nga=data_nga,
                data_ne=data_ne,
                legal_form_filter=legal_form_filter,
                secondary_filters=secondary_filters,
            ),
            extra_metadata={
                "nipt": nipt,
                "legal_form_filter": legal_form_filter,
                "canonical_legal_form_filter": canonical_legal_form,
                "secondary_filters": secondary_filters or {},
                "secondary_filter_labels": secondary_filter_labels or {},
                "data_nga": data_nga.isoformat() if data_nga else None,
                "data_ne": data_ne.isoformat() if data_ne else None,
                "form_data": form_data,
                "mode": "http",
            },
        )
        db.commit()

        external_key = self._build_external_key(
            nipt=nipt,
            data_nga=data_nga,
            data_ne=data_ne,
            legal_form_filter=legal_form_filter,
            secondary_filters=secondary_filters,
        )
        structured_row = self.upsert_structured_record(
            db,
            record_type="qkb_search_snapshot",
            external_key=external_key,
            title=f"QKB search snapshot {external_key}",
            source_url=response.url,
            content_hash=raw_row.content_hash,
            payload={
                "nipt": nipt,
                "legal_form_filter": legal_form_filter,
                "canonical_legal_form_filter": canonical_legal_form,
                "secondary_filters": secondary_filters or {},
                "secondary_filter_labels": secondary_filter_labels or {},
                "data_nga": data_nga.isoformat() if data_nga else None,
                "data_ne": data_ne.isoformat() if data_ne else None,
                "raw_fetch_id": raw_row.id,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "response": parsed_result.parsed_response,
            },
            published_at=utc_now_naive(),
        )
        db.commit()

        one_day_search = (
            data_nga is not None and data_ne is not None and data_nga == data_ne
        )

        return {
            "source_name": self.source_name,
            "nipt": nipt,
            "legal_form_filter": legal_form_filter,
            "canonical_legal_form_filter": canonical_legal_form,
            "secondary_filters": secondary_filters or {},
            "secondary_filter_labels": secondary_filter_labels or {},
            "data_nga": data_nga.isoformat() if data_nga else None,
            "data_ne": data_ne.isoformat() if data_ne else None,
            "raw_fetch_id": raw_row.id,
            "raw_fetch_ids": [raw_row.id],
            "structured_record_id": structured_row.id,
            "structured_record_ids": [structured_row.id],
            "external_key": external_key,
            "external_keys": [external_key],
            "status_code": response.status_code,
            "content_type": response.content_type,
            "url": response.url,
            "mode": "http",
            "records_found": parsed_result.records_found,
            "potentially_truncated": one_day_search and parsed_result.records_found == self.DAILY_RESULT_LIMIT,
        }

    def _build_form_data(
        self,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
        legal_form: str | None = None,
        secondary_filters: dict[str, str] | None = None,
    ) -> dict[str, str]:
        form_data = {
            "orderColumn": "0",
            "orderDir": "asc",
            "nipt": nipt or "",
            "emriISubjektit": "",
            "emriTregtar": "",
            "formeLigjore": legal_form or "",
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
        for field_name, field_value in (secondary_filters or {}).items():
            if field_name not in form_data:
                raise ValueError(f"Unsupported QKB search filter field: {field_name}")
            form_data[field_name] = field_value
        return form_data

    def _execute_and_parse_search(
        self,
        http: HttpClient,
        *,
        session_cookies: Any,
        form_data: dict[str, str],
    ) -> _ParsedSearchResult:
        response = self._execute_search_request(
            http,
            session_cookies=session_cookies,
            form_data=form_data,
        )
        page_text = response.content.decode("utf-8", errors="replace")
        parsed_response = self._extract_response_from_page(page_text)
        records = self._extract_response_records(parsed_response)
        return _ParsedSearchResult(
            response=response,
            parsed_response=parsed_response,
            records=records,
            records_found=len(records),
            business_nipts=self._extract_business_nipts(records),
        )

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
        legal_form_filter: str | None = None,
        secondary_filters: dict[str, str] | None = None,
    ) -> str:
        nipt_part = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "-",
            self._build_external_key_subject(
                nipt=nipt,
                legal_form_filter=legal_form_filter,
                secondary_filters=secondary_filters,
            ),
        ).strip("-")
        from_part = data_nga.isoformat() if data_nga else "none"
        to_part = data_ne.isoformat() if data_ne else "none"
        return f"qkb-search-{nipt_part}-{from_part}-{to_part}.html"

    def _build_external_key(
        self,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
        legal_form_filter: str | None = None,
        secondary_filters: dict[str, str] | None = None,
    ) -> str:
        return "|".join(
            [
                self._build_external_key_subject(
                    nipt=nipt,
                    legal_form_filter=legal_form_filter,
                    secondary_filters=secondary_filters,
                ),
                data_nga.isoformat() if data_nga else "none",
                data_ne.isoformat() if data_ne else "none",
            ]
        )

    @staticmethod
    def _build_external_key_subject(
        *,
        nipt: str | None = None,
        legal_form_filter: str | None = None,
        secondary_filters: dict[str, str] | None = None,
    ) -> str:
        subject_parts: list[str] = []
        if nipt:
            subject_parts.append(nipt)
        if legal_form_filter:
            subject_parts.append(
                f"legal_form:{canonicalize_qkb_legal_form(legal_form_filter) or legal_form_filter.strip()}"
            )
        for field_name, field_value in (secondary_filters or {}).items():
            subject_parts.append(
                f"{field_name}:{QkbSearchCollector._canonicalize_external_key_component(field_value)}"
            )
        return "|".join(subject_parts) if subject_parts else "all"

    @staticmethod
    def _canonicalize_external_key_component(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().upper()).strip("_")
        return slug or "UNKNOWN"

    @staticmethod
    def _run_mode_for_legal_form(canonical_legal_form: str | None) -> str:
        if canonical_legal_form is None:
            return RUN_MODE_DAILY_RANGE

        prefix = f"{RUN_MODE_DAILY_LEGAL_FORM}:"
        slug = re.sub(r"[^A-Z0-9]+", "", canonical_legal_form.upper()) or "UNKNOWN"
        if len(prefix) + len(slug) <= 50:
            return f"{prefix}{slug}"

        digest = hashlib.sha1(canonical_legal_form.encode("utf-8")).hexdigest()[:8]
        max_slug_length = max(1, 50 - len(prefix) - len(digest) - 1)
        return f"{prefix}{slug[:max_slug_length]}-{digest}"

    def _count_records(self, parsed_response: Any) -> int:
        return len(self._extract_response_records(parsed_response))

    @staticmethod
    def _extract_response_records(parsed_response: Any) -> list[dict[str, Any]]:
        if isinstance(parsed_response, list):
            return [item for item in parsed_response if isinstance(item, dict)]
        if isinstance(parsed_response, dict):
            data = parsed_response.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]

        return []

    @staticmethod
    def _extract_business_nipts(records: list[dict[str, Any]]) -> list[str]:
        return QkbSearchCollector._dedupe_preserving_order(
            str(record.get("nipti", "")).strip()
            for record in records
            if str(record.get("nipti", "")).strip()
        )

    @staticmethod
    def _dedupe_preserving_order(values: Any) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    @staticmethod
    def _extract_secondary_filter_candidates(
        search_form_text: str,
        *,
        field_preferences: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        parser = _SelectOptionParser(field_preferences)
        parser.feed(search_form_text)
        return [
            {
                "field_name": field_name,
                "options": parser.options_by_field[field_name],
            }
            for field_name in field_preferences
            if parser.options_by_field.get(field_name)
        ]

    def _extract_qarku_filter_options(self, search_form_text: str) -> list[dict[str, str]]:
        candidates = self._extract_secondary_filter_candidates(
            search_form_text,
            field_preferences=(self.SECONDARY_CHUNK_FIELD_QARKU,),
        )
        if not candidates:
            return []
        return candidates[0]["options"]

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
        run_mode: str = RUN_MODE_DAILY_RANGE,
    ) -> _DailyRunStart:
        existing_runs = db.scalars(
            select(QkbSearchRun)
            .where(
                QkbSearchRun.collector_name == self.source_name,
                QkbSearchRun.mode == run_mode,
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
                mode=run_mode,
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
            mode=run_mode,
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

    def _load_search_form(self, http: HttpClient) -> ResponsePayload:
        return http.get(settings.qkb_search_url)

    def _establish_search_session(self, http: HttpClient) -> Any:
        initial_response = self._load_search_form(http)
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
