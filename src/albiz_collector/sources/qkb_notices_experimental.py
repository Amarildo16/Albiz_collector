from __future__ import annotations

"""Experimental QKB notices collector kept outside supported production workflows."""

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import settings
from ..utils.hashing import sha256_bytes
from ..utils.http import HttpClient
from .base import CollectorBase

logger = logging.getLogger(__name__)


class ExperimentalQkbNoticesCollector(CollectorBase):
    """Experimental collector not included in supported CLI or scheduler flows."""

    source_name = "qkb_notices"

    def collect(self, db: Session, use_playwright: bool = False) -> dict[str, Any]:
        requested_mode = "playwright" if use_playwright else "http"
        rendered_pages: dict[str, bytes] = {}
        if use_playwright:
            rendered_pages, effective_mode = self._collect_with_playwright()
        else:
            effective_mode = "http"

        stats: dict[str, Any] = {
            "collector_status": "experimental_not_for_production",
            "index_saved": False,
            "categories_processed": 0,
            "records_upserted": 0,
            "requested_mode": requested_mode,
            "mode": effective_mode,
            "playwright_rendered_categories": len(rendered_pages),
            "playwright_fallback": requested_mode == "playwright" and effective_mode != "playwright",
        }

        with HttpClient() as http:
            index_response = http.get(settings.qkb_notices_index_url)
            self.save_raw_fetch(
                db,
                url=index_response.url,
                content=index_response.content,
                fetch_kind="index_page",
                status_code=index_response.status_code,
                content_type=index_response.content_type,
                filename="shpallje-index.html",
            )
            db.commit()
            stats["index_saved"] = True

            for category, url in settings.qkb_notice_categories.items():
                html: bytes
                final_url = url
                if category in rendered_pages:
                    html = rendered_pages[category]
                    status_code = 200
                    content_type = "text/html"
                else:
                    response = http.get(url)
                    html = response.content
                    final_url = response.url
                    status_code = response.status_code
                    content_type = response.content_type

                raw_row = self.save_raw_fetch(
                    db,
                    url=final_url,
                    content=html,
                    fetch_kind="category_page",
                    status_code=status_code,
                    content_type=content_type,
                    filename=f"{category}.html",
                    extra_metadata={
                        "category": category,
                        "collector_status": stats["collector_status"],
                        "mode": stats["mode"],
                        "requested_mode": stats["requested_mode"],
                    },
                )

                documents = self._parse_documents(url, html)
                if not documents:
                    content_hash = sha256_bytes(html)
                    self.upsert_structured_record(
                        db,
                        record_type="category_snapshot",
                        external_key=category,
                        title=category.replace("_", " ").title(),
                        source_url=url,
                        content_hash=content_hash,
                        payload={
                            "category": category,
                            "raw_fetch_id": raw_row.id,
                            "note": "No document links parsed. The page may be JS-driven or require tighter selectors.",
                        },
                    )
                    stats["records_upserted"] += 1
                else:
                    for idx, doc in enumerate(documents, start=1):
                        content_hash = sha256_bytes((doc["href"] + doc["title"]).encode("utf-8"))
                        self.upsert_structured_record(
                            db,
                            record_type="notice_document",
                            external_key=f"{category}:{doc['href']}",
                            title=doc["title"],
                            source_url=doc["href"],
                            content_hash=content_hash,
                            payload={
                                "category": category,
                                "raw_fetch_id": raw_row.id,
                                "ordinal": idx,
                                "text": doc["text"],
                            },
                            published_at=doc.get("published_at"),
                        )
                        stats["records_upserted"] += 1

                db.commit()
                stats["categories_processed"] += 1

        return stats

    def _parse_documents(self, base_url: str, html: bytes) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        documents: list[dict[str, Any]] = []
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            absolute_href = urljoin(base_url, href)
            text = " ".join(anchor.stripped_strings)
            title = text or absolute_href.rsplit("/", 1)[-1]

            looks_like_doc = bool(
                re.search(r"\.(pdf|docx?|xlsx?)($|\?)", absolute_href, re.I)
                or "download" in absolute_href.lower()
            )

            if settings.qkb_notices_parse_document_links_only and not looks_like_doc:
                continue

            if looks_like_doc or text:
                documents.append(
                    {
                        "href": absolute_href,
                        "title": title[:500],
                        "text": text[:4000],
                        "published_at": self._extract_date(text),
                    }
                )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in documents:
            key = item["href"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _extract_date(self, text: str) -> datetime | None:
        match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text)
        if not match:
            return None
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    def _collect_with_playwright(self) -> tuple[dict[str, bytes], str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            logger.warning("Playwright unavailable, falling back to HTTP mode: %s", exc)
            return {}, "http"

        rendered_pages: dict[str, bytes] = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=settings.qkb_notices_playwright_headless)
            page = browser.new_page()
            for category, url in settings.qkb_notice_categories.items():
                logger.info("Experimental Playwright collecting QKB category: %s", category)
                page.goto(url, wait_until="networkidle")

                try:
                    page.get_by_text(settings.qkb_notices_search_button_text, exact=True).click()
                except Exception:
                    logger.info("Search button not clicked for %s; saving rendered page as-is", category)

                page.wait_for_timeout(settings.qkb_notices_wait_ms)
                rendered_pages[category] = page.content().encode("utf-8")
            browser.close()
        return rendered_pages, "playwright"
