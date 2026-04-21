from __future__ import annotations

from pathlib import Path
import unittest

from albiz_collector.sources.qkb_search import QkbSearchCollector


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "qkb_search"


class QkbSearchParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = QkbSearchCollector()

    def test_extract_response_from_saved_fixture(self) -> None:
        html = (FIXTURES_DIR / "search-results-with-records.html").read_text(encoding="utf-8")

        parsed = self.collector._extract_response_from_page(html)

        self.assertIsInstance(parsed, list)
        self.assertGreaterEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["nipti"], "M61617507C")

    def test_extract_response_supports_direct_array_assignment(self) -> None:
        page = 'var response = [{"nipti": "K123", "statusiISubjektit": "Aprovuar"}];'

        parsed = self.collector._extract_response_from_page(page)

        self.assertEqual(parsed[0]["nipti"], "K123")

    def test_extract_response_raises_when_missing(self) -> None:
        with self.assertRaises(ValueError):
            self.collector._extract_response_from_page("<html><body>No response variable</body></html>")


if __name__ == "__main__":
    unittest.main()
