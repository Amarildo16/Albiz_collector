from __future__ import annotations

from pathlib import Path
import unittest

from albiz_collector.sources.app_exports import AppExportsCollector


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "app_exports"


class AppExportsParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = AppExportsCollector()

    def test_parse_index_discovers_years_and_filenames(self) -> None:
        html = (FIXTURES_DIR / "export-public-calls.html").read_bytes()

        parsed = self.collector._parse_index(html)

        self.assertEqual(sorted(parsed.keys()), [2010, 2025, 2026])
        self.assertEqual(
            parsed[2026]["filename"],
            "Procedurat e prokurimit - viti 2026 - Gjeneruar me 17042026.csv",
        )

    def test_parse_csv_preview_returns_rows(self) -> None:
        content = (FIXTURES_DIR / "app_procurement_preview.csv").read_bytes()

        preview = self.collector._parse_csv_preview(content)

        self.assertEqual(len(preview), 3)
        self.assertEqual(preview[0]["Numri_i_references"], "REF-80797-04-02-2026")
        self.assertEqual(preview[1]["Autoriteti_kontraktues"], "Tirana Parking")


if __name__ == "__main__":
    unittest.main()
