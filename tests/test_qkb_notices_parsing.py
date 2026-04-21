from __future__ import annotations

from pathlib import Path
import unittest

from albiz_collector.config import settings
from albiz_collector.sources.qkb_notices import QkbNoticesCollector


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "qkb_notices"


class QkbNoticesParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = QkbNoticesCollector()

    def test_parse_documents_extracts_absolute_links_dates_and_dedupes(self) -> None:
        html = (FIXTURES_DIR / "category-page.html").read_bytes()

        original = settings.qkb_notices_parse_document_links_only
        settings.qkb_notices_parse_document_links_only = True
        try:
            parsed = self.collector._parse_documents("https://format.qkb.gov.al/njoftime-gjyqesore/", html)
        finally:
            settings.qkb_notices_parse_document_links_only = original

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["href"], "https://format.qkb.gov.al/docs/notice-1.pdf")
        self.assertEqual(parsed[0]["published_at"].date().isoformat(), "2026-04-17")
        self.assertEqual(parsed[1]["href"], "https://format.qkb.gov.al/download?id=42")

    def test_extract_date_returns_none_for_invalid_dates(self) -> None:
        parsed = self.collector._extract_date("Court notice 31.02.2026")

        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
