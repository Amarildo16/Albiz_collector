from __future__ import annotations

import unittest

from albiz_collector.sources.qkb_document_actions import parse_qkb_document_action_evidence

from tests.support import fixture_path


class QkbDocumentActionParsingTests(unittest.TestCase):
    def test_extracts_document_action_evidence_from_saved_qkb_fixture(self) -> None:
        html = fixture_path("qkb_search", "search-results-with-records.html").read_text(
            encoding="utf-8"
        )

        evidence = parse_qkb_document_action_evidence(html)

        self.assertEqual(evidence.document_types, ("rpp", "simple", "historical"))
        self.assertTrue(evidence.references_fetch_and_display_pdf)
        self.assertTrue(evidence.references_download_button_press)
        self.assertEqual(
            evidence.full_url,
            "https://format.qkb.gov.al/wp-content/themes/twentytwentyfive-child/modules/search/national-registry/subject/",
        )
        self.assertIsNone(evidence.pdf_endpoint)

    def test_does_not_infer_pdf_endpoint_without_document_handler_fixture(self) -> None:
        html = """
        <div id="docPills">
            <button data-doc="historical">Historical</button>
        </div>
        <script>
            fetchAndDisplayPDF(currentRec.nipti, "historical", fullUrl);
            downloadButtonPress(currentRec.nipti, "historical", fullUrl);
        </script>
        """

        evidence = parse_qkb_document_action_evidence(html)

        self.assertEqual(evidence.document_types, ("historical",))
        self.assertTrue(evidence.references_fetch_and_display_pdf)
        self.assertTrue(evidence.references_download_button_press)
        self.assertIsNone(evidence.full_url)
        self.assertIsNone(evidence.pdf_endpoint)


if __name__ == "__main__":
    unittest.main()
