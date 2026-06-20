from __future__ import annotations

"""Rate-limited, database-backed OpenCorporates HTML financial enrichment."""

import time
from contextlib import nullcontext
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    NormalizedQkbSearchRow,
    OpenCorporatesCompanyProfile,
    OpenCorporatesFinancialYear,
)
from ..utils.http import ResponsePayload
from ..utils.time import utc_now_naive
from .opencorporates_financial_discovery import (
    normalize_opencorporates_nipt,
    opencorporates_company_url,
    parse_albanian_decimal,
    parse_opencorporates_company_page,
)

OPENCORPORATES_SOURCE_TYPE = "opencorporates_html"
PROFILE_STATUSES_ELIGIBLE_FOR_STALE_SKIP = frozenset({"ok", "missing_page", "no_financial_data"})
SHPK_SOURCE_LEGAL_FORM_VALUES = (
    "SHPK",
    "SH.P.K",
    "SH.P.K.",
    "Shoqeri me pergjegjesi te kufizuar",
    "Shoq\u00ebri me p\u00ebrgjegj\u00ebsi t\u00eb kufizuar",
)


class OpenCorporatesFinancialEnricher:
    """Fetch direct company pages and persist secondary HTML-derived financial data."""

    def __init__(
        self,
        http_client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        now_factory: Callable[[], datetime] = utc_now_naive,
    ) -> None:
        self._http_client = http_client
        self._sleeper = sleeper
        self._now_factory = now_factory

    def run(
        self,
        db: Session,
        *,
        limit: int = 100,
        offset: int = 0,
        delay_seconds: float = 1.0,
        force: bool = False,
        nipt: str | None = None,
        only_shpk: bool = True,
        stale_days: int = 30,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        _validate_run_options(
            limit=limit,
            offset=offset,
            delay_seconds=delay_seconds,
            stale_days=stale_days,
        )
        started_at = time.monotonic()
        now = self._now_factory()
        requested_nipt = normalize_opencorporates_nipt(nipt)
        selection = select_opencorporates_financial_nipts(
            db,
            limit=limit,
            offset=offset,
            nipt=requested_nipt,
            only_shpk=only_shpk,
            force=force,
            stale_before=now - timedelta(days=stale_days),
        )
        summary: dict[str, Any] = {
            "dataset": "opencorporates_financials",
            "source_type": OPENCORPORATES_SOURCE_TYPE,
            "requested_limit": limit,
            "offset": offset,
            "requested_nipt": requested_nipt,
            "only_shpk": only_shpk,
            "force": force,
            "stale_days": stale_days,
            "dry_run": dry_run,
            "selected_nipts": selection["selected_nipts"],
            "selected_nipt_count": len(selection["selected_nipts"]),
            "skipped_recent": selection["skipped_recent"],
            "skipped_offset": selection["skipped_offset"],
            "pages_found": 0,
            "pages_missing": 0,
            "companies_with_financial_data": 0,
            "financial_rows_upserted": 0,
            "parse_errors": 0,
            "http_errors": 0,
            "persistence_errors": 0,
            "http_requests_executed": 0,
            "errors": [],
        }
        if dry_run or not selection["selected_nipts"]:
            summary["elapsed_seconds"] = _elapsed_seconds(started_at)
            return summary

        request_count = 0
        with self._client_context() as http:
            for selected_nipt in selection["selected_nipts"]:
                fetch_result, request_count = self._fetch_company_page(
                    http,
                    nipt=selected_nipt,
                    delay_seconds=delay_seconds,
                    request_count=request_count,
                )
                summary["http_requests_executed"] = request_count
                _record_fetch_outcome(summary, fetch_result)

                try:
                    upsert_opencorporates_company_profile(db, fetch_result, fetched_at=now)
                    summary["financial_rows_upserted"] += upsert_opencorporates_financial_years(
                        db,
                        fetch_result,
                        fetched_at=now,
                    )
                    db.commit()
                except Exception as exc:  # Keep later NIPTs resumable after one database failure.
                    db.rollback()
                    summary["persistence_errors"] += 1
                    summary["errors"].append({"nipt": selected_nipt, "stage": "persistence", "error": str(exc)})

        summary["elapsed_seconds"] = _elapsed_seconds(started_at)
        return summary

    def _client_context(self):  # type: ignore[no-untyped-def]
        if self._http_client is not None:
            return nullcontext(self._http_client)
        return httpx.Client(
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            trust_env=True,
            headers={
                "User-Agent": settings.http_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sq,en;q=0.9",
            },
        )

    def _fetch_company_page(
        self,
        http: Any,
        *,
        nipt: str,
        delay_seconds: float,
        request_count: int,
    ) -> tuple[dict[str, Any], int]:
        canonical_nipt = normalize_opencorporates_nipt(nipt)
        if canonical_nipt is None:
            raise ValueError("nipt must not be empty")

        attempts: list[dict[str, Any]] = []
        url = opencorporates_company_url(canonical_nipt)
        response, request_count = self._request(
            http,
            url,
            delay_seconds=delay_seconds,
            request_count=request_count,
        )
        attempts.append(
            {
                "url": url,
                "status_code": response.get("status_code"),
                "error": response.get("error"),
            }
        )
        if response.get("error") is not None:
            return _error_result(
                nipt=canonical_nipt,
                source_url=url,
                http_status=response.get("status_code"),
                parse_status="http_error",
                error=response["error"],
                attempts=attempts,
            ), request_count

        status_code = response["status_code"]
        if status_code in {404, 410}:
            return _missing_page_result(canonical_nipt, response["url"], status_code, attempts), request_count
        if status_code >= 400:
            return _error_result(
                nipt=canonical_nipt,
                source_url=response["url"],
                http_status=status_code,
                parse_status="http_error",
                error=f"http_status_{status_code}",
                attempts=attempts,
            ), request_count

        try:
            parsed = parse_opencorporates_company_page(response["text"], page_url=response["url"])
        except Exception as exc:
            return _error_result(
                nipt=canonical_nipt,
                source_url=response["url"],
                http_status=status_code,
                parse_status="parse_error",
                error=f"{type(exc).__name__}: {exc}",
                attempts=attempts,
            ), request_count

        if parsed["page_exists"] is None:
            return _error_result(
                nipt=canonical_nipt,
                source_url=response["url"],
                http_status=status_code,
                parse_status="parse_error",
                error="access_blocked_or_javascript_challenge",
                attempts=attempts,
            ), request_count
        if parsed["page_exists"] is False:
            return _missing_page_result(canonical_nipt, response["url"], status_code, attempts), request_count

        return _parsed_page_result(
            nipt=canonical_nipt,
            source_url=response["url"],
            http_status=status_code,
            parsed=parsed,
            attempts=attempts,
        ), request_count

    def _request(
        self,
        http: Any,
        url: str,
        *,
        delay_seconds: float,
        request_count: int,
    ) -> tuple[dict[str, Any], int]:
        if request_count > 0 and delay_seconds:
            self._sleeper(delay_seconds)
        try:
            response = http.get(url)
        except httpx.HTTPError as exc:
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            return {
                "url": url,
                "status_code": status_code,
                "text": "",
                "error": f"{type(exc).__name__}: {exc}",
            }, request_count + 1
        except Exception as exc:
            return {
                "url": url,
                "status_code": None,
                "text": "",
                "error": f"{type(exc).__name__}: {exc}",
            }, request_count + 1

        if isinstance(response, ResponsePayload):
            return {
                "url": response.url,
                "status_code": response.status_code,
                "text": response.text or response.content.decode("utf-8", errors="replace"),
                "error": None,
            }, request_count + 1
        return {
            "url": str(response.url),
            "status_code": response.status_code,
            "text": response.text,
            "error": None,
        }, request_count + 1


def select_opencorporates_financial_nipts(
    db: Session,
    *,
    limit: int,
    offset: int,
    nipt: str | None,
    only_shpk: bool,
    force: bool,
    stale_before: datetime,
) -> dict[str, Any]:
    """Return deterministic exact-NIPT candidates, excluding recently completed work."""
    if nipt is not None:
        normalized_nipt = normalize_opencorporates_nipt(nipt)
        if normalized_nipt is None:
            return {"selected_nipts": [], "skipped_recent": 0, "skipped_offset": 0}
        profile = db.scalar(
            select(OpenCorporatesCompanyProfile).where(OpenCorporatesCompanyProfile.nipt == normalized_nipt)
        )
        if not force and _is_recent_completed_profile(profile, stale_before):
            return {"selected_nipts": [], "skipped_recent": 1, "skipped_offset": 0}
        return {"selected_nipts": [normalized_nipt], "skipped_recent": 0, "skipped_offset": 0}

    source_statement = select(NormalizedQkbSearchRow.business_nipt.label("nipt")).where(
        NormalizedQkbSearchRow.business_nipt.is_not(None),
        NormalizedQkbSearchRow.business_nipt != "",
    )
    if only_shpk:
        source_statement = source_statement.where(
            NormalizedQkbSearchRow.legal_form.in_(SHPK_SOURCE_LEGAL_FORM_VALUES)
        )
    source_nipts = source_statement.group_by(NormalizedQkbSearchRow.business_nipt).subquery()
    statement = (
        select(
            source_nipts.c.nipt,
            OpenCorporatesCompanyProfile.last_fetched_at,
            OpenCorporatesCompanyProfile.parse_status,
        )
        .outerjoin(OpenCorporatesCompanyProfile, OpenCorporatesCompanyProfile.nipt == source_nipts.c.nipt)
        .order_by(source_nipts.c.nipt)
    )

    selected_nipts: list[str] = []
    seen_nipts: set[str] = set()
    skipped_recent = 0
    skipped_offset = 0
    candidate_position = 0
    for candidate_nipt, last_fetched_at, parse_status in db.execute(statement):
        normalized_nipt = normalize_opencorporates_nipt(candidate_nipt)
        if normalized_nipt is None or normalized_nipt in seen_nipts:
            continue
        seen_nipts.add(normalized_nipt)
        if candidate_position < offset:
            candidate_position += 1
            skipped_offset += 1
            continue
        candidate_position += 1
        if not force and _is_recent_completed(last_fetched_at, parse_status, stale_before):
            skipped_recent += 1
            continue
        selected_nipts.append(normalized_nipt)
        if len(selected_nipts) >= limit:
            break

    return {
        "selected_nipts": selected_nipts,
        "skipped_recent": skipped_recent,
        "skipped_offset": skipped_offset,
    }


def upsert_opencorporates_company_profile(
    db: Session,
    fetch_result: dict[str, Any],
    *,
    fetched_at: datetime,
) -> OpenCorporatesCompanyProfile:
    profile = db.scalar(
        select(OpenCorporatesCompanyProfile).where(OpenCorporatesCompanyProfile.nipt == fetch_result["nipt"])
    )
    if profile is None:
        profile = OpenCorporatesCompanyProfile(
            nipt=fetch_result["nipt"],
            source_url=fetch_result["source_url"],
            page_found=fetch_result["page_found"],
            http_status=fetch_result["http_status"],
            company_name=fetch_result.get("company_name"),
            has_financial_data=fetch_result["has_financial_data"],
            has_revenue_data=fetch_result["has_revenue_data"],
            has_profit_data=fetch_result["has_profit_data"],
            financial_year_count=fetch_result["financial_year_count"],
            min_financial_year=fetch_result.get("min_financial_year"),
            max_financial_year=fetch_result.get("max_financial_year"),
            financial_document_links_count=fetch_result["financial_document_links_count"],
            historical_extract_links_count=fetch_result["historical_extract_links_count"],
            visible_csv_json_controls=fetch_result["visible_csv_json_controls"],
            parse_status=fetch_result["parse_status"],
            parse_error=fetch_result.get("parse_error"),
            last_fetched_at=fetched_at,
            created_at=fetched_at,
            updated_at=fetched_at,
        )
        db.add(profile)
        return profile

    profile.source_url = fetch_result["source_url"]
    profile.page_found = fetch_result["page_found"]
    profile.http_status = fetch_result["http_status"]
    profile.company_name = fetch_result.get("company_name")
    profile.has_financial_data = fetch_result["has_financial_data"]
    profile.has_revenue_data = fetch_result["has_revenue_data"]
    profile.has_profit_data = fetch_result["has_profit_data"]
    profile.financial_year_count = fetch_result["financial_year_count"]
    profile.min_financial_year = fetch_result.get("min_financial_year")
    profile.max_financial_year = fetch_result.get("max_financial_year")
    profile.financial_document_links_count = fetch_result["financial_document_links_count"]
    profile.historical_extract_links_count = fetch_result["historical_extract_links_count"]
    profile.visible_csv_json_controls = fetch_result["visible_csv_json_controls"]
    profile.parse_status = fetch_result["parse_status"]
    profile.parse_error = fetch_result.get("parse_error")
    profile.last_fetched_at = fetched_at
    profile.updated_at = fetched_at
    return profile


def upsert_opencorporates_financial_years(
    db: Session,
    fetch_result: dict[str, Any],
    *,
    fetched_at: datetime,
) -> int:
    if fetch_result["parse_status"] not in {"ok", "no_financial_data"}:
        return 0

    upserted = 0
    for financial_row in fetch_result["financial_rows"]:
        existing = db.scalar(
            select(OpenCorporatesFinancialYear).where(
                OpenCorporatesFinancialYear.nipt == fetch_result["nipt"],
                OpenCorporatesFinancialYear.year == financial_row["year"],
                OpenCorporatesFinancialYear.source_type == OPENCORPORATES_SOURCE_TYPE,
            )
        )
        revenue_raw, revenue_amount = _financial_metric_values(financial_row.get("revenue"))
        profit_raw, profit_amount = _financial_metric_values(financial_row.get("profit_before_tax"))
        if existing is None:
            db.add(
                OpenCorporatesFinancialYear(
                    nipt=fetch_result["nipt"],
                    year=financial_row["year"],
                    revenue_raw=revenue_raw,
                    revenue_amount=revenue_amount,
                    profit_before_tax_raw=profit_raw,
                    profit_before_tax_amount=profit_amount,
                    source_type=OPENCORPORATES_SOURCE_TYPE,
                    source_url=fetch_result["source_url"],
                    fetched_at=fetched_at,
                    created_at=fetched_at,
                    updated_at=fetched_at,
                )
            )
        else:
            existing.revenue_raw = revenue_raw
            existing.revenue_amount = revenue_amount
            existing.profit_before_tax_raw = profit_raw
            existing.profit_before_tax_amount = profit_amount
            existing.source_url = fetch_result["source_url"]
            existing.fetched_at = fetched_at
            existing.updated_at = fetched_at
        upserted += 1
    return upserted


def _parsed_page_result(
    *,
    nipt: str,
    source_url: str,
    http_status: int,
    parsed: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    financial_rows = parsed["financial_rows"]
    has_revenue_data = any("revenue" in row for row in financial_rows)
    has_profit_data = any("profit_before_tax" in row for row in financial_rows)
    parse_status = "ok" if financial_rows else "no_financial_data"
    years = parsed["available_financial_years"]
    return {
        "nipt": nipt,
        "source_url": source_url,
        "http_status": http_status,
        "page_found": True,
        "company_name": parsed.get("company_name"),
        "has_financial_data": bool(financial_rows),
        "has_revenue_data": has_revenue_data,
        "has_profit_data": has_profit_data,
        "financial_year_count": len(years),
        "min_financial_year": min(years) if years else None,
        "max_financial_year": max(years) if years else None,
        "financial_document_links_count": len(parsed["financial_document_links"]),
        "historical_extract_links_count": len(parsed["historical_extract_links"]),
        "visible_csv_json_controls": bool(parsed["visible_export_controls"]),
        "parse_status": parse_status,
        "parse_error": None,
        "financial_rows": financial_rows,
        "attempts": attempts,
    }


def _missing_page_result(
    nipt: str,
    source_url: str,
    http_status: int | None,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return _base_fetch_result(
        nipt=nipt,
        source_url=source_url,
        http_status=http_status,
        page_found=False,
        parse_status="missing_page",
        parse_error=None,
        attempts=attempts,
    )


def _error_result(
    *,
    nipt: str,
    source_url: str,
    http_status: int | None,
    parse_status: str,
    error: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return _base_fetch_result(
        nipt=nipt,
        source_url=source_url,
        http_status=http_status,
        page_found=None,
        parse_status=parse_status,
        parse_error=error,
        attempts=attempts,
    )


def _base_fetch_result(
    *,
    nipt: str,
    source_url: str,
    http_status: int | None,
    page_found: bool | None,
    parse_status: str,
    parse_error: str | None,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "nipt": nipt,
        "source_url": source_url,
        "http_status": http_status,
        "page_found": page_found,
        "company_name": None,
        "has_financial_data": False,
        "has_revenue_data": False,
        "has_profit_data": False,
        "financial_year_count": 0,
        "min_financial_year": None,
        "max_financial_year": None,
        "financial_document_links_count": 0,
        "historical_extract_links_count": 0,
        "visible_csv_json_controls": False,
        "parse_status": parse_status,
        "parse_error": parse_error,
        "financial_rows": [],
        "attempts": attempts,
    }


def _financial_metric_values(metric: dict[str, Any] | None) -> tuple[str | None, Decimal | None]:
    if metric is None:
        return None, None
    raw_text = metric.get("raw_text")
    if not isinstance(raw_text, str):
        return None, None
    return raw_text, parse_albanian_decimal(raw_text)


def _record_fetch_outcome(summary: dict[str, Any], fetch_result: dict[str, Any]) -> None:
    if fetch_result["page_found"] is True:
        summary["pages_found"] += 1
    elif fetch_result["page_found"] is False:
        summary["pages_missing"] += 1

    if fetch_result["has_financial_data"]:
        summary["companies_with_financial_data"] += 1
    if fetch_result["parse_status"] == "parse_error":
        summary["parse_errors"] += 1
    if fetch_result["parse_status"] == "http_error":
        summary["http_errors"] += 1
    if fetch_result["parse_status"] in {"parse_error", "http_error"}:
        summary["errors"].append(
            {
                "nipt": fetch_result["nipt"],
                "stage": fetch_result["parse_status"],
                "error": fetch_result["parse_error"],
            }
        )


def _is_recent_completed_profile(profile: OpenCorporatesCompanyProfile | None, stale_before: datetime) -> bool:
    if profile is None:
        return False
    return _is_recent_completed(profile.last_fetched_at, profile.parse_status, stale_before)


def _is_recent_completed(last_fetched_at: datetime | None, parse_status: str | None, stale_before: datetime) -> bool:
    return (
        last_fetched_at is not None
        and last_fetched_at >= stale_before
        and parse_status in PROFILE_STATUSES_ELIGIBLE_FOR_STALE_SKIP
    )


def _validate_run_options(*, limit: int, offset: int, delay_seconds: float, stale_days: int) -> None:
    if limit < 1:
        raise ValueError("limit must be positive")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    if stale_days < 0:
        raise ValueError("stale_days must be non-negative")


def _elapsed_seconds(started_at: float) -> float:
    return round(time.monotonic() - started_at, 3)
