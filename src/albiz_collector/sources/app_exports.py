from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import settings
from ..utils.hashing import sha256_bytes
from ..utils.http import HttpClient
from .base import CollectorBase

logger = logging.getLogger(__name__)


class AppExportsCollector(CollectorBase):
    source_name = "app_exports"

    def collect(self, db: Session, years: list[int] | None = None) -> dict[str, Any]:
        years = years or settings.app_export_years
        stats: dict[str, Any] = {
            "index_page_saved": False,
            "years_considered": years,
            "exports_saved": 0,
            "records_upserted": 0,
        }

        with HttpClient() as http:
            index_response = http.get(settings.app_export_page_url)
            self.save_raw_fetch(
                db,
                url=index_response.url,
                content=index_response.content,
                fetch_kind="index_page",
                status_code=index_response.status_code,
                content_type=index_response.content_type,
                filename="export-public-calls.html",
            )
            db.commit()
            stats["index_page_saved"] = True

            available = self._parse_index(index_response.content)
            if available:
                years = sorted(set(years).intersection(available.keys())) or years
                stats["index_years_discovered"] = sorted(available.keys())

            for year in years:
                download_url = settings.app_export_download_url_template.format(year=year)
                try:
                    response = http.get(download_url)
                except Exception as exc:
                    logger.exception("Failed to download APP export for year=%s", year)
                    stats.setdefault("errors", []).append({"year": year, "error": str(exc)})
                    continue

                filename = f"app_procurement_{year}.csv"
                raw_row = self.save_raw_fetch(
                    db,
                    url=response.url,
                    content=response.content,
                    fetch_kind="year_export",
                    status_code=response.status_code,
                    content_type=response.content_type,
                    filename=filename,
                    extra_metadata={"year": year},
                )

                parsed = self._parse_csv_preview(response.content)
                content_hash = sha256_bytes(response.content)
                self.upsert_structured_record(
                    db,
                    record_type="procurement_export_year",
                    external_key=str(year),
                    title=f"APP procurement export {year}",
                    source_url=response.url,
                    content_hash=content_hash,
                    payload={
                        "year": year,
                        "raw_fetch_id": raw_row.id,
                        "preview": parsed,
                        "row_count_previewed": len(parsed),
                    },
                    published_at=datetime.utcnow(),
                )
                db.commit()
                stats["exports_saved"] += 1
                stats["records_upserted"] += 1

        return stats

    def _parse_index(self, html: bytes) -> dict[int, dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        mapping: dict[int, dict[str, str]] = {}

        for row in soup.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if len(cells) < 2:
                continue
            year_text, filename = cells[0], cells[1]
            if re.fullmatch(r"20\d{2}", year_text) and filename.lower().endswith(".csv"):
                mapping[int(year_text)] = {"filename": filename}

        if mapping:
            return mapping

        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            match = re.search(r"^(20\d{2})\s+(.+\.csv)$", line.strip())
            if match:
                year = int(match.group(1))
                mapping[year] = {"filename": match.group(2)}
        return mapping

    def _parse_csv_preview(self, content: bytes, limit: int = 5) -> list[dict[str, str]]:
        try:
            decoded = content.decode("utf-8-sig", errors="replace")
            sample = io.StringIO(decoded)
            reader = csv.DictReader(sample)
            rows: list[dict[str, str]] = []
            for idx, row in enumerate(reader):
                rows.append({k: (v or "")[:500] for k, v in row.items()})
                if idx + 1 >= limit:
                    break
            return rows
        except Exception:
            logger.exception("Failed to parse APP CSV preview")
            return []
