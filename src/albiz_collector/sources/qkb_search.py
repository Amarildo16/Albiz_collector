from __future__ import annotations

import codecs
import json
import logging
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..utils.http import HttpClient
from .base import CollectorBase

logger = logging.getLogger(__name__)


class QkbSearchCollector(CollectorBase):
    source_name = "qkb_search"

    def collect(
        self,
        db: Session,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
        use_playwright: bool = False,
    ) -> dict[str, Any]:
        form_data = self._build_form_data(nipt=nipt, data_nga=data_nga, data_ne=data_ne)

        if use_playwright:
            html = self._collect_with_playwright(nipt=nipt, data_nga=data_nga, data_ne=data_ne)
            status_code = 200
            content_type = "text/html"
            final_url = settings.qkb_search_url
        else:
            with HttpClient() as http:
                initial_response = http.get(settings.qkb_search_url)
                response = http.post(
                    settings.qkb_search_url,
                    data=form_data,
                    headers=self._build_headers(),
                    cookies=initial_response.cookies,
                )
                html = response.content
                status_code = response.status_code
                content_type = response.content_type
                final_url = response.url

        raw_row = self.save_raw_fetch(
            db,
            url=final_url,
            content=html,
            fetch_kind="search_results_page",
            status_code=status_code,
            content_type=content_type,
            filename=self._build_filename(nipt=nipt, data_nga=data_nga, data_ne=data_ne),
            extra_metadata={
                "nipt": nipt,
                "data_nga": data_nga.isoformat() if data_nga else None,
                "data_ne": data_ne.isoformat() if data_ne else None,
                "form_data": form_data,
                "mode": "playwright" if use_playwright else "http",
            },
        )
        db.commit()

        page_text = html.decode("utf-8", errors="replace")
        try:
            parsed_response = self._extract_response_from_page(page_text)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse QKB search response from saved raw fetch {raw_row.id}"
            ) from exc

        content_hash = raw_row.content_hash
        external_key = self._build_external_key(nipt=nipt, data_nga=data_nga, data_ne=data_ne)

        structured_row = self.upsert_structured_record(
            db,
            record_type="qkb_search_snapshot",
            external_key=external_key,
            title=f"QKB search snapshot {external_key}",
            source_url=final_url,
            content_hash=content_hash,
            payload={
                "nipt": nipt,
                "data_nga": data_nga.isoformat() if data_nga else None,
                "data_ne": data_ne.isoformat() if data_ne else None,
                "raw_fetch_id": raw_row.id,
                "status_code": status_code,
                "content_type": content_type,
                "response": parsed_response,
            },
            published_at=datetime.utcnow(),
        )
        db.commit()

        return {
            "source_name": self.source_name,
            "nipt": nipt,
            "data_nga": data_nga.isoformat() if data_nga else None,
            "data_ne": data_ne.isoformat() if data_ne else None,
            "raw_fetch_id": raw_row.id,
            "structured_record_id": structured_row.id,
            "external_key": external_key,
            "status_code": status_code,
            "content_type": content_type,
            "url": final_url,
            "mode": "playwright" if use_playwright else "http",
            "records_found": self._count_records(parsed_response),
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
            "dataNga": data_nga.isoformat() if data_nga else "",
            "dataNe": data_ne.isoformat() if data_ne else "",
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

    def _collect_with_playwright(
        self,
        nipt: str | None = None,
        data_nga: date | None = None,
        data_ne: date | None = None,
    ) -> bytes:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Playwright is required for QKB search browser collection") from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=settings.qkb_search_playwright_headless)
            page = browser.new_page()
            page.goto(settings.qkb_search_url, wait_until="networkidle")

            try:
                if nipt:
                    page.locator(settings.qkb_search_nipt_selector).fill(nipt)
            except Exception:
                logger.warning("Could not fill NIPT field")

            try:
                if data_nga:
                    page.locator(settings.qkb_search_date_from_selector).fill(data_nga.isoformat())
            except Exception:
                logger.warning("Could not fill dataNga field")

            try:
                if data_ne:
                    page.locator(settings.qkb_search_date_to_selector).fill(data_ne.isoformat())
            except Exception:
                logger.warning("Could not fill dataNe field")

            try:
                page.get_by_text(settings.qkb_search_button_text, exact=True).click()
            except Exception:
                logger.info("Search button not clicked; saving rendered page as-is")

            page.wait_for_timeout(settings.qkb_search_wait_ms)
            html = page.content().encode("utf-8")
            browser.close()
            return html