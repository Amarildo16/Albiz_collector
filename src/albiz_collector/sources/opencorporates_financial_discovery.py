from __future__ import annotations

"""Small, HTML-first OpenCorporates financial discovery helper.

This module intentionally does not persist fetched pages, download PDFs, or
participate in scheduled collection. It is a controlled feasibility probe for
the public company-page representation only.
"""

import csv
import json
import random
import re
import time
import unicodedata
from collections import Counter
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT, settings
from ..models import NormalizedAppExportRow, NormalizedQkbSearchRow
from ..qkb_legal_forms import is_qkb_shpk_legal_form
from ..utils.http import ResponsePayload

OPENCORPORATES_COMPANY_URL_TEMPLATE = "https://opencorporates.al/sq/nipt/{nipt}"
DEFAULT_DISCOVERY_SAMPLE_SIZE = 60
DEFAULT_REQUEST_DELAY_SECONDS = 0.5
DEFAULT_STRUCTURED_LINK_PROBE_LIMIT = 3
MAX_CONSECUTIVE_UNAVAILABLE_PAGES = 3

_FINANCIAL_SECTION_KEYWORDS = (
    "te dhenat financiare",
    "informacione financiare",
    "financial information",
    "financial data",
    "xhiro vjetore",
    "annual revenue",
    "fitimi para tatimit",
    "profit before tax",
)
_REVENUE_KEYWORDS = ("xhiro", "revenue", "te ardhura", "annual turnover")
_PROFIT_KEYWORDS = ("fitimi para tatimit", "fitim para tatimit", "profit before tax")
_FINANCIAL_DOCUMENT_KEYWORDS = (
    "financ",
    "bilanc",
    "pasqyr",
    "xhiro",
    "fitim",
    "revenue",
    "annual report",
)
_HISTORICAL_LINK_KEYWORDS = ("historik", "historical", "ekstrakt", "extract")
_ACCESS_BLOCK_MARKERS = (
    "enable javascript and cookies to continue",
    "cf_chl",
    "challenge-platform",
    "just a moment",
)
_NOT_FOUND_MARKERS = ("page not found", "faqja nuk u gjet", "nuk u gjet")
_YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_INLINE_REVENUE_PATTERN = re.compile(
    r"(?:xhiro\s+vjetore|annual\s+revenue)[^0-9]{0,80}(?P<year>(?:19|20)\d{2})\s*:\s*(?P<amount>[-0-9\s.,\u00a0]+)",
    re.IGNORECASE,
)
_INLINE_PROFIT_PATTERN = re.compile(
    r"(?:fitimi\s+para\s+tatimit|fitim\s+para\s+tatimit|profit\s+before\s+tax)[^0-9]{0,80}(?P<year>(?:19|20)\d{2})\s*:\s*(?P<amount>[-0-9\s.,\u00a0]+)",
    re.IGNORECASE,
)


def parse_albanian_decimal(value: str | None) -> Decimal | None:
    """Parse a displayed Albanian-style amount without guessing absent values."""
    if value is None:
        return None

    numeric = re.sub(r"[^0-9,\.\-\s\u00a0]", "", value).replace("\u00a0", "")
    numeric = re.sub(r"\s+", "", numeric)
    if not numeric or numeric in {"-", ".", ","}:
        return None

    negative = numeric.startswith("-")
    numeric = numeric.replace("-", "")
    if not numeric or not any(character.isdigit() for character in numeric):
        return None

    comma_count = numeric.count(",")
    dot_count = numeric.count(".")
    if comma_count and dot_count:
        decimal_separator = "," if numeric.rfind(",") > numeric.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        normalized = numeric.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif comma_count:
        normalized = _normalize_single_separator_amount(numeric, ",")
    elif dot_count:
        normalized = _normalize_single_separator_amount(numeric, ".")
    else:
        normalized = numeric

    if negative:
        normalized = f"-{normalized}"
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def parse_opencorporates_company_page(html: str | bytes, *, page_url: str) -> dict[str, Any]:
    """Extract visible, non-authoritative discovery signals from one company page."""
    soup = BeautifulSoup(html, "lxml")
    visible_text = _normalize_text(soup.get_text(" ", strip=True))
    access_blocked = any(marker in visible_text for marker in _ACCESS_BLOCK_MARKERS)
    not_found = any(marker in visible_text for marker in _NOT_FOUND_MARKERS)

    page_exists: bool | None
    if access_blocked:
        page_exists = None
    else:
        page_exists = not not_found

    financial_section_exists = any(keyword in visible_text for keyword in _FINANCIAL_SECTION_KEYWORDS)
    financial_rows = _extract_yearly_financial_rows(soup)
    financial_years = sorted({row["year"] for row in financial_rows})
    links = _extract_links(soup, page_url)

    return {
        "page_exists": page_exists,
        "access_blocked": access_blocked,
        "company_name": _extract_company_name(soup),
        "financial_info_section_exists": financial_section_exists,
        "financial_rows": financial_rows,
        "available_financial_years": financial_years,
        "financial_document_links": _select_links(links, _is_financial_document_link, financial_section_exists),
        "historical_extract_links": _select_links(links, _is_historical_extract_link, financial_section_exists),
        "csv_links": _select_links(links, _is_csv_link, financial_section_exists),
        "json_links": _select_links(links, _is_json_link, financial_section_exists),
        "visible_export_controls": _visible_export_controls(visible_text),
    }


class OpenCorporatesFinancialDiscovery:
    """Controlled, non-persistent HTML discovery against a small local cohort."""

    def __init__(
        self,
        http_client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http_client = http_client
        self._sleeper = sleeper

    def run(
        self,
        db: Session,
        *,
        sample_size: int = DEFAULT_DISCOVERY_SAMPLE_SIZE,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        structured_link_probe_limit: int = DEFAULT_STRUCTURED_LINK_PROBE_LIMIT,
        seed: int = 20260619,
    ) -> dict[str, Any]:
        sample = build_opencorporates_discovery_sample(db, sample_size=sample_size, seed=seed)
        return self.discover_sample(
            sample,
            requested_sample_size=sample_size,
            request_delay_seconds=request_delay_seconds,
            structured_link_probe_limit=structured_link_probe_limit,
            seed=seed,
        )

    def discover_sample(
        self,
        sample: list[dict[str, Any]],
        *,
        requested_sample_size: int,
        request_delay_seconds: float,
        structured_link_probe_limit: int,
        seed: int,
    ) -> dict[str, Any]:
        if request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must be non-negative")
        if structured_link_probe_limit < 0:
            raise ValueError("structured_link_probe_limit must be non-negative")

        company_results: list[dict[str, Any]] = []
        requests_executed = 0
        consecutive_unavailable_pages = 0
        stopped_early_reason: str | None = None

        with self._client_context() as http:
            for sample_entry in sample:
                company_result, request_count = self._fetch_company_page(
                    http,
                    nipt=sample_entry["nipt"],
                    request_delay_seconds=request_delay_seconds,
                    request_count=requests_executed,
                )
                requests_executed = request_count
                company_result["selection_cohorts"] = sample_entry["selection_cohorts"]
                company_results.append(company_result)

                if company_result.get("page_exists") is None:
                    consecutive_unavailable_pages += 1
                else:
                    consecutive_unavailable_pages = 0
                if consecutive_unavailable_pages >= MAX_CONSECUTIVE_UNAVAILABLE_PAGES:
                    stopped_early_reason = (
                        "repeated_access_blocks"
                        if company_result.get("access_blocked")
                        else "repeated_unavailable_pages"
                    )
                    break

            structured_link_results, structured_request_count = self._probe_visible_structured_links(
                http,
                company_results,
                probe_limit=structured_link_probe_limit,
                request_delay_seconds=request_delay_seconds,
                request_count=requests_executed,
            )
            requests_executed += structured_request_count

        return _build_discovery_result(
            requested_sample_size=requested_sample_size,
            sample=sample,
            company_results=company_results,
            structured_link_results=structured_link_results,
            requests_executed=requests_executed,
            request_delay_seconds=request_delay_seconds,
            structured_link_probe_limit=structured_link_probe_limit,
            seed=seed,
            stopped_early_reason=stopped_early_reason,
        )

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
        request_delay_seconds: float,
        request_count: int,
    ) -> tuple[dict[str, Any], int]:
        attempts: list[dict[str, Any]] = []
        candidate_urls = _company_urls_for_nipt(nipt)
        for index, url in enumerate(candidate_urls):
            response, request_count = self._request(
                http,
                url,
                request_delay_seconds=request_delay_seconds,
                request_count=request_count,
            )
            attempts.append({
                "url": url,
                "status_code": response.get("status_code"),
                "error": response.get("error"),
            })
            if response.get("error") is not None:
                return {
                    "business_nipt": nipt,
                    "source_type": "opencorporates_html",
                    "page_url": url,
                    "urls_tried": attempts,
                    "status_code": response.get("status_code"),
                    "page_exists": None,
                    "access_blocked": False,
                    "failure_reason": response["error"],
                }, request_count

            status_code = response["status_code"]
            parsed = parse_opencorporates_company_page(response["text"], page_url=response["url"])
            parsed.update(
                {
                    "business_nipt": nipt,
                    "source_type": "opencorporates_html",
                    "page_url": response["url"],
                    "urls_tried": attempts,
                    "status_code": status_code,
                    "content_type": response.get("content_type"),
                }
            )
            if parsed["access_blocked"]:
                parsed["failure_reason"] = "access_blocked_or_javascript_challenge"
                return parsed, request_count
            if status_code in {404, 410} or parsed["page_exists"] is False:
                if index + 1 < len(candidate_urls):
                    continue
                parsed["page_exists"] = False
                parsed["failure_reason"] = f"http_status_{status_code}" if status_code else "page_not_found"
                return parsed, request_count
            if status_code >= 400:
                parsed["page_exists"] = None
                parsed["failure_reason"] = f"http_status_{status_code}"
                return parsed, request_count
            if not parsed["financial_info_section_exists"]:
                parsed["failure_reason"] = "financial_section_not_visible"
            return parsed, request_count

        raise AssertionError("At least one company URL candidate is required")

    def _probe_visible_structured_links(
        self,
        http: Any,
        company_results: Iterable[dict[str, Any]],
        *,
        probe_limit: int,
        request_delay_seconds: float,
        request_count: int,
    ) -> tuple[list[dict[str, Any]], int]:
        probes: list[dict[str, Any]] = []
        if probe_limit == 0:
            return probes, 0

        local_request_count = request_count
        for company in company_results:
            if len(probes) >= probe_limit:
                break
            links = [("json", link) for link in company.get("json_links", [])]
            links += [("csv", link) for link in company.get("csv_links", [])]
            if not links:
                continue

            link_type, link = links[0]
            response, local_request_count = self._request(
                http,
                link["url"],
                request_delay_seconds=request_delay_seconds,
                request_count=local_request_count,
            )
            probe = {
                "business_nipt": company["business_nipt"],
                "link_type": link_type,
                "url": link["url"],
                "status_code": response.get("status_code"),
                "content_type": response.get("content_type"),
                "error": response.get("error"),
                "structured_data_detected": False,
                "financial_fields_detected": False,
            }
            if response.get("error") is None and response.get("status_code", 0) < 400:
                structured, financial_fields = _inspect_structured_response(link_type, response["text"])
                probe["structured_data_detected"] = structured
                probe["financial_fields_detected"] = financial_fields
            probes.append(probe)

        return probes, local_request_count - request_count

    def _request(
        self,
        http: Any,
        url: str,
        *,
        request_delay_seconds: float,
        request_count: int,
    ) -> tuple[dict[str, Any], int]:
        if request_count > 0 and request_delay_seconds:
            self._sleeper(request_delay_seconds)
        try:
            response = http.get(url)
        except httpx.HTTPError as exc:
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            text = exc.response.text if isinstance(exc, httpx.HTTPStatusError) else ""
            return {
                "url": url,
                "status_code": status_code,
                "content_type": None,
                "text": text,
                "error": f"{type(exc).__name__}: {exc}",
            }, request_count + 1
        except Exception as exc:  # Defensive: experimental discovery must report, not abort, a cohort.
            return {
                "url": url,
                "status_code": None,
                "content_type": None,
                "text": "",
                "error": f"{type(exc).__name__}: {exc}",
            }, request_count + 1

        if isinstance(response, ResponsePayload):
            return {
                "url": response.url,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "text": response.text or response.content.decode("utf-8", errors="replace"),
                "error": None,
            }, request_count + 1
        return {
            "url": str(response.url),
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "text": response.text,
            "error": None,
        }, request_count + 1


def build_opencorporates_discovery_sample(
    db: Session,
    *,
    sample_size: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Build a small, deduplicated cohort from local normalized APP/QKB rows."""
    if sample_size < 1:
        raise ValueError("sample_size must be positive")

    per_cohort = max(1, sample_size // 5)
    sample: dict[str, set[str]] = {}
    _add_sample_cohort(sample, "top_app_winner_value", _top_app_nipts_by_winner_value(db, per_cohort))
    _add_sample_cohort(sample, "top_app_contract_count", _top_app_nipts_by_contract_count(db, per_cohort))

    shpk_candidates = _load_shpk_candidates(db)
    _add_sample_cohort(sample, "old_shpk", [nipt for nipt, _ in shpk_candidates[:per_cohort]])
    _add_sample_cohort(sample, "new_shpk", [nipt for nipt, _ in shpk_candidates[-per_cohort:][::-1]])

    random_nipts = [nipt for nipt, _ in shpk_candidates]
    random.Random(seed).shuffle(random_nipts)
    _add_sample_cohort(sample, "random_shpk", random_nipts[:per_cohort])

    if len(sample) < sample_size:
        _add_sample_cohort(sample, "random_shpk_fill", random_nipts[per_cohort:])

    return [
        {"nipt": nipt, "selection_cohorts": sorted(cohorts)}
        for nipt, cohorts in list(sample.items())[:sample_size]
    ]


def write_opencorporates_financial_discovery_reports(
    result: dict[str, Any],
    *,
    output_dir: str | Path = "reports",
) -> dict[str, str]:
    directory = Path(output_dir)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "opencorporates_financial_discovery.json"
    markdown_path = directory / "opencorporates_financial_discovery.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    markdown_path.write_text(_render_markdown_report(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _normalize_single_separator_amount(value: str, separator: str) -> str:
    parts = value.split(separator)
    last_part = parts[-1]
    if len(last_part) in {1, 2}:
        return f"{''.join(parts[:-1])}.{last_part}"
    return "".join(parts)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    accentless = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", accentless).strip().lower()


def _extract_company_name(soup: BeautifulSoup) -> str | None:
    for heading in soup.find_all(["h2", "h1"]):
        value = heading.get_text(" ", strip=True)
        if value and _normalize_text(value) != "open corporates .al":
            return _clean_company_heading(value)
    meta = soup.find("meta", attrs={"property": "og:title"})
    if isinstance(meta, Tag):
        value = meta.get("content")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_yearly_financial_rows(soup: BeautifulSoup) -> list[dict[str, Any]]:
    by_year: dict[int, dict[str, Any]] = {}
    for table in soup.find_all("table"):
        table_rows = table.find_all("tr")
        if not table_rows:
            continue
        header_cells = table_rows[0].find_all(["th", "td"])
        headers = [_normalize_text(cell.get_text(" ", strip=True)) for cell in header_cells]
        year_index = _field_index(headers, ("vit", "year"))
        revenue_index = _field_index(headers, _REVENUE_KEYWORDS)
        profit_index = _field_index(headers, _PROFIT_KEYWORDS)
        if year_index is None or (revenue_index is None and profit_index is None):
            continue

        for row in table_rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= year_index:
                continue
            year = _extract_year(cells[year_index].get_text(" ", strip=True))
            if year is None:
                continue
            financial_row = by_year.setdefault(year, {"year": year})
            _set_metric_from_cell(financial_row, "revenue", cells, revenue_index)
            _set_metric_from_cell(financial_row, "profit_before_tax", cells, profit_index)

    page_text = soup.get_text(" ", strip=True)
    _add_inline_metrics(by_year, page_text, _INLINE_REVENUE_PATTERN, "revenue")
    _add_inline_metrics(by_year, page_text, _INLINE_PROFIT_PATTERN, "profit_before_tax")

    return [by_year[year] for year in sorted(by_year)]


def _set_metric_from_cell(
    financial_row: dict[str, Any],
    metric_name: str,
    cells: list[Tag],
    index: int | None,
) -> None:
    if index is None or len(cells) <= index:
        return
    raw_text = cells[index].get_text(" ", strip=True)
    normalized_amount = parse_albanian_decimal(raw_text)
    if normalized_amount is None:
        return
    financial_row[metric_name] = {
        "raw_text": raw_text,
        "normalized_amount": float(normalized_amount),
        "source_type": "opencorporates_html",
    }


def _add_inline_metrics(
    by_year: dict[int, dict[str, Any]],
    page_text: str,
    pattern: re.Pattern[str],
    metric_name: str,
) -> None:
    for match in pattern.finditer(page_text):
        raw_text = match.group("amount").strip()
        normalized_amount = parse_albanian_decimal(raw_text)
        if normalized_amount is None:
            continue
        year = int(match.group("year"))
        financial_row = by_year.setdefault(year, {"year": year})
        financial_row.setdefault(
            metric_name,
            {
                "raw_text": raw_text,
                "normalized_amount": float(normalized_amount),
                "source_type": "opencorporates_html",
            },
        )


def _field_index(headers: list[str], keywords: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if any(keyword in header for keyword in keywords):
            return index
    return None


def _extract_year(value: str) -> int | None:
    match = _YEAR_PATTERN.search(value)
    return int(match.group(0)) if match else None


def _extract_links(soup: BeautifulSoup, page_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        url = urljoin(page_url, href.strip())
        if url in seen_urls or urlparse(url).scheme not in {"http", "https"}:
            continue
        seen_urls.add(url)
        links.append({"url": url, "text": anchor.get_text(" ", strip=True)})
    return links


def _clean_company_heading(value: str) -> str:
    for marker in (" Zotëruese", " Zoteruese", " Më shumë", " Me shume", " Informacioni"):
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.strip()


def _select_links(
    links: list[dict[str, str]],
    predicate: Callable[[dict[str, str], bool], bool],
    financial_section_exists: bool,
) -> list[dict[str, str]]:
    return [link for link in links if predicate(link, financial_section_exists)]


def _is_financial_document_link(link: dict[str, str], financial_section_exists: bool) -> bool:
    normalized = _normalize_text(f"{link['text']} {link['url']}")
    path = urlparse(link["url"]).path.lower()
    is_document_path = "/documents/" in path or path.endswith((".pdf", ".xlsx", ".xls", ".csv"))
    return is_document_path and any(keyword in normalized for keyword in _FINANCIAL_DOCUMENT_KEYWORDS)


def _is_historical_extract_link(link: dict[str, str], financial_section_exists: bool) -> bool:
    normalized = _normalize_text(f"{link['text']} {link['url']}")
    return any(keyword in normalized for keyword in _HISTORICAL_LINK_KEYWORDS)


def _is_json_link(link: dict[str, str], financial_section_exists: bool) -> bool:
    normalized = _normalize_text(f"{link['text']} {link['url']}")
    return ".json" in normalized or "format=json" in normalized or "format json" in normalized


def _is_csv_link(link: dict[str, str], financial_section_exists: bool) -> bool:
    normalized = _normalize_text(f"{link['text']} {link['url']}")
    return ".csv" in normalized or "format=csv" in normalized or "format csv" in normalized


def _visible_export_controls(visible_text: str) -> list[str]:
    controls = []
    if re.search(r"\bcsv\b", visible_text):
        controls.append("csv")
    if re.search(r"\bjson\b", visible_text):
        controls.append("json")
    return controls


def _company_urls_for_nipt(nipt: str) -> list[str]:
    values = [nipt.strip().upper(), nipt.strip().lower()]
    return list(dict.fromkeys(OPENCORPORATES_COMPANY_URL_TEMPLATE.format(nipt=value) for value in values if value))


def _inspect_structured_response(link_type: str, text: str) -> tuple[bool, bool]:
    if link_type == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False, False
        keys = _collect_json_keys(parsed)
        return isinstance(parsed, (dict, list)), _contains_financial_field(keys)

    try:
        rows = list(csv.reader(text.splitlines()))
    except csv.Error:
        return False, False
    if len(rows) < 2 or not rows[0]:
        return False, False
    headers = [_normalize_text(value) for value in rows[0]]
    return True, _contains_financial_field(headers)


def _collect_json_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            keys.append(_normalize_text(str(key)))
            keys.extend(_collect_json_keys(nested_value))
    elif isinstance(value, list):
        for nested_value in value[:10]:
            keys.extend(_collect_json_keys(nested_value))
    return keys


def _contains_financial_field(values: Iterable[str]) -> bool:
    keywords = _REVENUE_KEYWORDS + _PROFIT_KEYWORDS
    return any(any(keyword in value for keyword in keywords) for value in values)


def _top_app_nipts_by_winner_value(db: Session, limit: int) -> list[str]:
    statement = (
        select(NormalizedAppExportRow.winner_nipt)
        .where(NormalizedAppExportRow.winner_nipt.is_not(None))
        .group_by(NormalizedAppExportRow.winner_nipt)
        .order_by(func.sum(func.coalesce(NormalizedAppExportRow.winner_value_amount, 0)).desc())
        .limit(limit)
    )
    return [nipt for nipt in db.scalars(statement) if nipt]


def _top_app_nipts_by_contract_count(db: Session, limit: int) -> list[str]:
    statement = (
        select(NormalizedAppExportRow.winner_nipt)
        .where(NormalizedAppExportRow.winner_nipt.is_not(None))
        .group_by(NormalizedAppExportRow.winner_nipt)
        .order_by(func.count(NormalizedAppExportRow.id).desc())
        .limit(limit)
    )
    return [nipt for nipt in db.scalars(statement) if nipt]


def _load_shpk_candidates(db: Session) -> list[tuple[str, Any]]:
    statement = (
        select(
            NormalizedQkbSearchRow.business_nipt,
            NormalizedQkbSearchRow.legal_form,
            NormalizedQkbSearchRow.registration_date,
        )
        .where(
            NormalizedQkbSearchRow.business_nipt.is_not(None),
            NormalizedQkbSearchRow.registration_date.is_not(None),
        )
        .order_by(NormalizedQkbSearchRow.registration_date, NormalizedQkbSearchRow.business_nipt)
    )
    candidates: dict[str, Any] = {}
    for nipt, legal_form, registration_date in db.execute(statement):
        if nipt and is_qkb_shpk_legal_form(legal_form):
            candidates.setdefault(nipt, registration_date)
    return sorted(candidates.items(), key=lambda item: (item[1], item[0]))


def _add_sample_cohort(sample: dict[str, set[str]], cohort: str, nipts: Iterable[str]) -> None:
    for nipt in nipts:
        if nipt not in sample:
            sample[nipt] = set()
        sample[nipt].add(cohort)


def _build_discovery_result(
    *,
    requested_sample_size: int,
    sample: list[dict[str, Any]],
    company_results: list[dict[str, Any]],
    structured_link_results: list[dict[str, Any]],
    requests_executed: int,
    request_delay_seconds: float,
    structured_link_probe_limit: int,
    seed: int,
    stopped_early_reason: str | None,
) -> dict[str, Any]:
    pages_found = [item for item in company_results if item.get("page_exists") is True]
    pages_missing = [item for item in company_results if item.get("page_exists") is False]
    pages_unavailable = [item for item in company_results if item.get("page_exists") is None]
    financial_year_lists = [item["available_financial_years"] for item in pages_found if item.get("available_financial_years")]
    all_financial_years = [year for years in financial_year_lists for year in years]
    example_records = [item for item in pages_found if item.get("financial_rows")][:5]
    failure_reasons = Counter(item["failure_reason"] for item in company_results if item.get("failure_reason"))

    summary = {
        "sample_size_requested": requested_sample_size,
        "sample_size_selected": len(sample),
        "company_pages_attempted": len(company_results),
        "pages_found": len(pages_found),
        "pages_missing": len(pages_missing),
        "pages_unavailable": len(pages_unavailable),
        "companies_with_revenue_data": sum(
            any("revenue" in row for row in item.get("financial_rows", [])) for item in pages_found
        ),
        "companies_with_profit_before_tax_data": sum(
            any("profit_before_tax" in row for row in item.get("financial_rows", [])) for item in pages_found
        ),
        "average_financial_years_found": round(mean(map(len, financial_year_lists)), 2) if financial_year_lists else 0,
        "min_financial_year_found": min(all_financial_years) if all_financial_years else None,
        "max_financial_year_found": max(all_financial_years) if all_financial_years else None,
        "companies_with_financial_document_links": sum(bool(item.get("financial_document_links")) for item in pages_found),
        "companies_with_historical_extract_links": sum(bool(item.get("historical_extract_links")) for item in pages_found),
        "companies_with_json_or_csv_links": sum(
            bool(item.get("json_links") or item.get("csv_links")) for item in pages_found
        ),
        "companies_with_visible_export_controls_without_direct_links": sum(
            bool(item.get("visible_export_controls"))
            and not (item.get("json_links") or item.get("csv_links"))
            for item in pages_found
        ),
        "structured_link_probes_attempted": len(structured_link_results),
        "structured_link_probes_with_financial_data": sum(
            item.get("structured_data_detected") and item.get("financial_fields_detected")
            for item in structured_link_results
        ),
        "total_http_requests_executed": requests_executed,
        "stopped_early": stopped_early_reason is not None,
        "stopped_early_reason": stopped_early_reason,
    }
    return {
        "discovery_type": "opencorporates_financial_discovery",
        "status": "experimental_not_for_production",
        "source_type": "opencorporates_html",
        "request_policy": {
            "company_page_html_only": True,
            "bulk_pdf_downloads": False,
            "structured_link_probe_limit": structured_link_probe_limit,
            "request_delay_seconds": request_delay_seconds,
            "max_consecutive_unavailable_pages": MAX_CONSECUTIVE_UNAVAILABLE_PAGES,
        },
        "sample_seed": seed,
        "sample": sample,
        "summary": summary,
        "company_results": company_results,
        "structured_link_results": structured_link_results,
        "example_parsed_records": example_records,
        "parsing_failures": dict(sorted(failure_reasons.items())),
        "recommended_next_step": _recommend_next_step(summary),
    }


def _recommend_next_step(summary: dict[str, Any]) -> str:
    if summary["stopped_early"] or summary["pages_unavailable"]:
        return (
            "Do not build production enrichment yet. First obtain permission or identify a stable, documented access path "
            "because the sample encountered unavailable or anti-bot-protected pages."
        )
    if summary["structured_link_probes_with_financial_data"]:
        return (
            "Manually validate the small structured JSON/CSV examples and their source semantics before designing any "
            "production enrichment path."
        )
    if summary["companies_with_revenue_data"] or summary["companies_with_profit_before_tax_data"]:
        return (
            "Manually validate a few HTML-extracted financial rows against their displayed company pages before deciding "
            "whether a rate-limited secondary enrichment is warranted."
        )
    return (
        "OpenCorporates has not demonstrated usable visible financial data in this sample. Do not build production "
        "enrichment until a manual sample identifies a stable, documented financial-data representation."
    )


def _render_markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# OpenCorporates Financial Discovery",
        "",
        "Status: experimental discovery only. No pages, PDFs, or records were persisted to the project database.",
        "",
        "## Summary",
        "",
        f"- Sample selected: {summary['sample_size_selected']} of {summary['sample_size_requested']} requested NIPTs",
        f"- Company pages attempted: {summary['company_pages_attempted']}",
        f"- Pages found/missing/unavailable: {summary['pages_found']}/{summary['pages_missing']}/{summary['pages_unavailable']}",
        f"- Companies with revenue/profit data: {summary['companies_with_revenue_data']}/{summary['companies_with_profit_before_tax_data']}",
        f"- Financial years: average {summary['average_financial_years_found']}, range {summary['min_financial_year_found']} to {summary['max_financial_year_found']}",
        f"- Financial document links: {summary['companies_with_financial_document_links']}",
        f"- Historical extract links: {summary['companies_with_historical_extract_links']}",
        f"- JSON/CSV links: {summary['companies_with_json_or_csv_links']}",
        f"- Visible CSV/JSON controls without direct links: {summary['companies_with_visible_export_controls_without_direct_links']}",
        f"- Structured probes with financial fields: {summary['structured_link_probes_with_financial_data']}",
        f"- HTTP requests executed: {summary['total_http_requests_executed']}",
        f"- Stopped early: {summary['stopped_early']} ({summary['stopped_early_reason']})",
        "",
        "## Example Parsed Records",
        "",
    ]
    examples = result["example_parsed_records"]
    if examples:
        for item in examples:
            lines.append(f"- `{item['business_nipt']}`: {json.dumps(item['financial_rows'], ensure_ascii=False)}")
    else:
        lines.append("- No financial rows were parsed from the attempted pages.")

    lines.extend(["", "## Parsing Failures", ""])
    failures = result["parsing_failures"]
    if failures:
        lines.extend(f"- `{reason}`: {count}" for reason, count in failures.items())
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Recommended Next Step", "", result["recommended_next_step"], ""])
    return "\n".join(lines)
