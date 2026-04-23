from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from ..config import settings
from ..sources.app_exports import AppExportsCollector
from ..utils.http import HttpClient


class SmokeCheckFailure(RuntimeError):
    """Raised when a supported live source no longer matches expected contracts."""


def evaluate_app_source_contract(content: bytes) -> dict[str, Any]:
    collector = AppExportsCollector()
    available_years = collector._parse_index(content)
    if not available_years:
        raise SmokeCheckFailure(
            "APP export index is reachable but no export years could be parsed from the page."
        )

    page_text = content.decode("utf-8", errors="replace")
    download_hint_present = "GetData/ExportDocument?year=" in page_text
    if not download_hint_present:
        raise SmokeCheckFailure(
            "APP export index no longer advertises the expected ExportDocument?year=... download hint."
        )

    years = sorted(available_years)
    return {
        "source_name": "app_exports",
        "checks": {
            "parsed_year_count": len(years),
            "first_year": years[0],
            "last_year": years[-1],
            "download_hint_present": download_hint_present,
        },
    }


def evaluate_qkb_search_source_contract(content: bytes) -> dict[str, Any]:
    soup = BeautifulSoup(content, "lxml")

    form_count = len(soup.select("form"))
    nipt_field_present = _selector_present(soup, settings.qkb_search_nipt_selector)
    data_nga_field_present = _selector_present(soup, settings.qkb_search_date_from_selector)
    data_ne_field_present = _selector_present(soup, settings.qkb_search_date_to_selector)
    submit_controls_present = bool(soup.select("button, input[type='submit']"))

    missing_requirements: list[str] = []
    if form_count == 0:
        missing_requirements.append("search form")
    if not nipt_field_present:
        missing_requirements.append(f"NIPT selector {settings.qkb_search_nipt_selector!r}")
    if not data_nga_field_present:
        missing_requirements.append(f"date-from selector {settings.qkb_search_date_from_selector!r}")
    if not data_ne_field_present:
        missing_requirements.append(f"date-to selector {settings.qkb_search_date_to_selector!r}")
    if not submit_controls_present:
        missing_requirements.append("submit control")

    if missing_requirements:
        raise SmokeCheckFailure(
            "QKB search page is reachable but missing expected contract elements: "
            + ", ".join(missing_requirements)
        )

    return {
        "source_name": "qkb_search",
        "checks": {
            "form_count": form_count,
            "nipt_field_present": nipt_field_present,
            "data_nga_field_present": data_nga_field_present,
            "data_ne_field_present": data_ne_field_present,
            "submit_controls_present": submit_controls_present,
        },
    }


def run_app_source_contract_smoke_check() -> dict[str, Any]:
    with HttpClient() as http:
        response = http.get(settings.app_export_page_url)

    result = evaluate_app_source_contract(response.content)
    result["url"] = response.url
    result["status_code"] = response.status_code
    return result


def run_qkb_search_source_contract_smoke_check() -> dict[str, Any]:
    with HttpClient() as http:
        response = http.get(settings.qkb_search_url)

    result = evaluate_qkb_search_source_contract(response.content)
    result["url"] = response.url
    result["status_code"] = response.status_code
    return result


def _selector_present(soup: BeautifulSoup, selector: str) -> bool:
    try:
        return soup.select_one(selector) is not None
    except Exception as exc:
        raise SmokeCheckFailure(f"Configured selector {selector!r} is invalid: {exc}") from exc
