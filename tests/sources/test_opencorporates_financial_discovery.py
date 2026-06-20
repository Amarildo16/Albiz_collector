from __future__ import annotations

import unittest
from decimal import Decimal

from albiz_collector.sources.opencorporates_financial_discovery import (
    OpenCorporatesFinancialDiscovery,
    opencorporates_company_url,
    parse_albanian_decimal,
    parse_opencorporates_company_page,
)
from albiz_collector.utils.http import ResponsePayload


REPRESENTATIVE_COMPANY_HTML = """
<html>
  <body>
    <h1>Shembull SHPK</h1>
    <section id="financials">
      <h2>Të dhënat financiare</h2>
      <a href="/sq/banka/">Shoqëri Financiare Bankare</a>
      <table>
        <thead>
          <tr><th>Viti</th><th>Xhiro Vjetore</th><th>Fitimi Para Tatimit</th></tr>
        </thead>
        <tbody>
          <tr><td>2022</td><td>79 495 669,00</td><td>1 250 000,50</td></tr>
          <tr><td>2023</td><td>1.234.567,89</td><td>0,00</td></tr>
        </tbody>
      </table>
      <a href="/documents/financials-2023.pdf">Pasqyrat financiare 2023</a>
      <a href="/documents/historical-extract.pdf">Ekstrakt historik</a>
      <a href="/exports/financials.csv">CSV</a>
      <a href="/api/company-financials.json">JSON</a>
    </section>
  </body>
</html>
"""


class _FakeHttpClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def get(self, url: str) -> ResponsePayload:
        self.calls.append(url)
        text = self._responses[url]
        return ResponsePayload(
            url=url,
            status_code=200,
            content_type="application/json" if url.endswith(".json") else "text/html",
            content=text.encode("utf-8"),
            text=text,
            cookies=None,
        )


class _UnavailableHttpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str) -> ResponsePayload:
        self.calls.append(url)
        raise OSError("network unavailable")


class _StatusFakeHttpClient:
    def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def get(self, url: str) -> ResponsePayload:
        self.calls.append(url)
        status_code, text = self._responses[url]
        return ResponsePayload(
            url=url,
            status_code=status_code,
            content_type="text/html",
            content=text.encode("utf-8"),
            text=text,
            cookies=None,
        )


class OpenCorporatesFinancialDiscoveryTests(unittest.TestCase):
    def test_company_url_uses_one_canonical_uppercase_nipt(self) -> None:
        self.assertEqual(
            opencorporates_company_url(" l01409006d "),
            "https://opencorporates.al/sq/nipt/L01409006D",
        )

    def test_parse_albanian_decimal_handles_grouped_comma_amounts(self) -> None:
        self.assertEqual(parse_albanian_decimal("79 495 669,00"), Decimal("79495669.00"))
        self.assertEqual(parse_albanian_decimal("1.234.567,89"), Decimal("1234567.89"))
        self.assertEqual(parse_albanian_decimal("ALL 1 250 000,50"), Decimal("1250000.50"))
        self.assertIsNone(parse_albanian_decimal("nuk ka të dhëna"))

    def test_extracts_yearly_revenue_and_profit_rows_from_html(self) -> None:
        parsed = parse_opencorporates_company_page(
            REPRESENTATIVE_COMPANY_HTML,
            page_url="https://opencorporates.al/sq/nipt/K12345678A",
        )

        self.assertTrue(parsed["page_exists"])
        self.assertEqual(parsed["company_name"], "Shembull SHPK")
        self.assertTrue(parsed["financial_info_section_exists"])
        self.assertEqual(parsed["available_financial_years"], [2022, 2023])
        self.assertEqual(parsed["financial_rows"][0]["revenue"]["raw_text"], "79 495 669,00")
        self.assertEqual(parsed["financial_rows"][0]["revenue"]["normalized_amount"], 79495669.0)
        self.assertEqual(parsed["financial_rows"][0]["profit_before_tax"]["normalized_amount"], 1250000.5)
        self.assertEqual(parsed["financial_rows"][1]["profit_before_tax"]["normalized_amount"], 0.0)
        self.assertEqual(parsed["financial_rows"][0]["revenue"]["source_type"], "opencorporates_html")

    def test_handles_page_without_financial_section(self) -> None:
        parsed = parse_opencorporates_company_page(
            "<html><body><h1>No Finance SHPK</h1><p>Registry profile only.</p></body></html>",
            page_url="https://opencorporates.al/sq/nipt/K12345678A",
        )

        self.assertTrue(parsed["page_exists"])
        self.assertFalse(parsed["financial_info_section_exists"])
        self.assertEqual(parsed["financial_rows"], [])
        self.assertEqual(parsed["available_financial_years"], [])

    def test_extracts_inline_financial_rows_from_live_style_markup(self) -> None:
        parsed = parse_opencorporates_company_page(
            """
            <html><body>
              <h1>Open Corporates .al</h1>
              <h2>Example SHPK Zotëruese e disa koncesioneve Më shumë</h2>
              <h5>Informacione Financiare</h5>
              <table><tr><td>
                Fitimi para Tatimit(Lekë) 2023: 3 353 702 977,00<br>
                Xhiro Vjetore(Lekë) 2023:10 838 140 013,00<br>
                Xhiro Vjetore(Lekë) 2022:8 048 659 194,00
              </td></tr></table>
            </body></html>
            """,
            page_url="https://opencorporates.al/sq/nipt/K12345678A",
        )

        self.assertEqual(parsed["company_name"], "Example SHPK")
        self.assertTrue(parsed["financial_info_section_exists"])
        self.assertEqual(parsed["available_financial_years"], [2022, 2023])
        self.assertEqual(parsed["financial_rows"][0]["revenue"]["normalized_amount"], 8048659194.0)
        self.assertEqual(parsed["financial_rows"][1]["revenue"]["normalized_amount"], 10838140013.0)
        self.assertEqual(parsed["financial_rows"][1]["profit_before_tax"]["normalized_amount"], 3353702977.0)

    def test_detects_financial_document_historical_json_and_csv_links(self) -> None:
        parsed = parse_opencorporates_company_page(
            REPRESENTATIVE_COMPANY_HTML,
            page_url="https://opencorporates.al/sq/nipt/K12345678A",
        )

        self.assertEqual(parsed["financial_document_links"][0]["url"], "https://opencorporates.al/documents/financials-2023.pdf")
        self.assertEqual(parsed["historical_extract_links"][0]["url"], "https://opencorporates.al/documents/historical-extract.pdf")
        self.assertEqual(parsed["csv_links"][0]["url"], "https://opencorporates.al/exports/financials.csv")
        self.assertEqual(parsed["json_links"][0]["url"], "https://opencorporates.al/api/company-financials.json")

    def test_records_visible_export_controls_without_inventing_urls(self) -> None:
        parsed = parse_opencorporates_company_page(
            "<html><body><button>CSV</button><button>JSON</button></body></html>",
            page_url="https://opencorporates.al/sq/nipt/K12345678A",
        )

        self.assertEqual(parsed["visible_export_controls"], ["csv", "json"])
        self.assertEqual(parsed["csv_links"], [])
        self.assertEqual(parsed["json_links"], [])

    def test_discovery_probes_only_visible_structured_links(self) -> None:
        company_url = "https://opencorporates.al/sq/nipt/K12345678A"
        json_url = "https://opencorporates.al/api/company-financials.json"
        http = _FakeHttpClient(
            {
                company_url: REPRESENTATIVE_COMPANY_HTML,
                json_url: '{"financials": [{"year": 2023, "revenue": 123.45}]}',
            }
        )
        sleep_calls: list[float] = []

        result = OpenCorporatesFinancialDiscovery(http_client=http, sleeper=sleep_calls.append).discover_sample(
            [{"nipt": "K12345678A", "selection_cohorts": ["random_shpk"]}],
            requested_sample_size=1,
            request_delay_seconds=0.25,
            structured_link_probe_limit=1,
            seed=1,
        )

        self.assertEqual(http.calls, [company_url, json_url])
        self.assertEqual(sleep_calls, [0.25])
        self.assertEqual(result["summary"]["pages_found"], 1)
        self.assertEqual(result["summary"]["total_http_requests_executed"], 2)
        self.assertEqual(result["summary"]["structured_link_probes_attempted"], 1)
        self.assertEqual(result["summary"]["structured_link_probes_with_financial_data"], 1)
        self.assertTrue(result["structured_link_results"][0]["structured_data_detected"])
        self.assertTrue(result["structured_link_results"][0]["financial_fields_detected"])

    def test_discovery_stops_after_repeated_unavailable_pages(self) -> None:
        http = _UnavailableHttpClient()
        result = OpenCorporatesFinancialDiscovery(http_client=http, sleeper=lambda _: None).discover_sample(
            [
                {"nipt": f"K1234567{index}A", "selection_cohorts": ["random_shpk"]}
                for index in range(5)
            ],
            requested_sample_size=5,
            request_delay_seconds=0,
            structured_link_probe_limit=0,
            seed=1,
        )

        self.assertEqual(len(http.calls), 3)
        self.assertEqual(result["summary"]["company_pages_attempted"], 3)
        self.assertTrue(result["summary"]["stopped_early"])
        self.assertEqual(result["summary"]["stopped_early_reason"], "repeated_unavailable_pages")

    def test_discovery_does_not_retry_a_missing_page_with_lowercase_nipt(self) -> None:
        company_url = "https://opencorporates.al/sq/nipt/L01409006D"
        http = _StatusFakeHttpClient(
            {company_url: (404, "<html><body>Page not found</body></html>")}
        )

        result = OpenCorporatesFinancialDiscovery(http_client=http, sleeper=lambda _: None).discover_sample(
            [{"nipt": " l01409006d ", "selection_cohorts": ["random_shpk"]}],
            requested_sample_size=1,
            request_delay_seconds=0,
            structured_link_probe_limit=0,
            seed=1,
        )

        self.assertEqual(http.calls, [company_url])
        self.assertEqual(result["summary"]["total_http_requests_executed"], 1)
        self.assertEqual(result["summary"]["pages_missing"], 1)


if __name__ == "__main__":
    unittest.main()
