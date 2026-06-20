from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import select

from albiz_collector.db import Base
from albiz_collector.models import (
    NormalizedQkbSearchRow,
    OpenCorporatesCompanyProfile,
    OpenCorporatesFinancialYear,
    StructuredRecord,
)
from albiz_collector.sources.opencorporates_financials import (
    OpenCorporatesFinancialEnricher,
    select_opencorporates_financial_nipts,
)
from albiz_collector.utils.http import ResponsePayload
from tests.support import isolated_db_environment


FINANCIAL_HTML = """
<html><body>
  <h1>Open Corporates .al</h1>
  <h2>Example SHPK Zotëruese e disa koncesioneve</h2>
  <h5>Informacione Financiare</h5>
  <table><tr><td>
    Fitimi para Tatimit(Lekë) 2022: 1 250 000,50<br>
    Xhiro Vjetore(Lekë) 2022:79 495 669,00<br>
    Fitimi para Tatimit(Lekë) 2023: 0,00<br>
    Xhiro Vjetore(Lekë) 2023:80 000 000,00
  </td></tr></table>
  <a href="/documents/bilanci/financials-2023.pdf">Pasqyrat financiare 2023</a>
  <a href="/documents/dokumenta/historical.pdf">Ekstrakt historik</a>
  <button>CSV</button><button>JSON</button>
</body></html>
"""


class _FakeHttpClient:
    def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str) -> ResponsePayload:
        self.calls.append(url)
        status_code, text = self.responses[url]
        return ResponsePayload(
            url=url,
            status_code=status_code,
            content_type="text/html",
            content=text.encode("utf-8"),
            text=text,
            cookies=None,
        )


def _company_url(nipt: str) -> str:
    return f"https://opencorporates.al/sq/nipt/{nipt}"


def _add_qkb_row(
    db,
    *,
    row_ordinal: int,
    nipt: str,
    legal_form: str,
) -> None:
    db.add(
        NormalizedQkbSearchRow(
            structured_record_id=1,
            snapshot_external_key="qkb-fixture",
            source_name="qkb_search",
            result_ordinal=row_ordinal,
            business_nipt=nipt,
            legal_form=legal_form,
            registration_date=date(2010, 1, row_ordinal),
        )
    )


class OpenCorporatesFinancialEnrichmentTests(unittest.TestCase):
    def test_selection_is_deterministic_and_filters_to_known_shpk_forms(self) -> None:
        stale_before = datetime(2026, 5, 20)
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                db.add(
                    StructuredRecord(
                        id=1,
                        source_name="qkb_search",
                        record_type="qkb_search_snapshot",
                        external_key="qkb-fixture",
                        content_hash="qkb-hash",
                    )
                )
                _add_qkb_row(db, row_ordinal=1, nipt="K12345678A", legal_form="SHPK")
                _add_qkb_row(
                    db,
                    row_ordinal=2,
                    nipt="J12345678B",
                    legal_form="Shoqeri me pergjegjesi te kufizuar",
                )
                _add_qkb_row(db, row_ordinal=3, nipt="L12345678C", legal_form="Person Fizik")
                db.commit()

                shpk_selection = select_opencorporates_financial_nipts(
                    db,
                    limit=10,
                    offset=0,
                    nipt=None,
                    only_shpk=True,
                    force=True,
                    stale_before=stale_before,
                )
                all_forms_selection = select_opencorporates_financial_nipts(
                    db,
                    limit=10,
                    offset=0,
                    nipt=None,
                    only_shpk=False,
                    force=True,
                    stale_before=stale_before,
                )

        self.assertEqual(shpk_selection["selected_nipts"], ["J12345678B", "K12345678A"])
        self.assertEqual(all_forms_selection["selected_nipts"], ["J12345678B", "K12345678A", "L12345678C"])

    def test_recent_completed_profile_is_skipped_unless_force_is_used(self) -> None:
        now = datetime(2026, 6, 19, 12, 0, 0)
        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                db.add(
                    OpenCorporatesCompanyProfile(
                        nipt="K12345678A",
                        source_url=_company_url("K12345678A"),
                        page_found=True,
                        http_status=200,
                        has_financial_data=True,
                        has_revenue_data=True,
                        has_profit_data=True,
                        financial_year_count=1,
                        financial_document_links_count=0,
                        historical_extract_links_count=0,
                        visible_csv_json_controls=False,
                        parse_status="ok",
                        last_fetched_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.commit()

                skipped = select_opencorporates_financial_nipts(
                    db,
                    limit=1,
                    offset=0,
                    nipt="K12345678A",
                    only_shpk=True,
                    force=False,
                    stale_before=now - timedelta(days=30),
                )
                forced = select_opencorporates_financial_nipts(
                    db,
                    limit=1,
                    offset=0,
                    nipt="K12345678A",
                    only_shpk=True,
                    force=True,
                    stale_before=now - timedelta(days=30),
                )

        self.assertEqual(skipped["selected_nipts"], [])
        self.assertEqual(skipped["skipped_recent"], 1)
        self.assertEqual(forced["selected_nipts"], ["K12345678A"])

    def test_run_upserts_profile_and_financial_year_rows(self) -> None:
        nipt = "K12345678A"
        input_nipt = " k12345678a "
        now = datetime(2026, 6, 19, 12, 0, 0)
        http = _FakeHttpClient({_company_url(nipt): (200, FINANCIAL_HTML)})
        enricher = OpenCorporatesFinancialEnricher(
            http_client=http,
            sleeper=lambda _: None,
            now_factory=lambda: now,
        )

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                first_result = enricher.run(db, nipt=input_nipt, delay_seconds=0, force=True)
                http.responses[_company_url(nipt)] = (200, FINANCIAL_HTML.replace("80 000 000,00", "81 000 000,00"))
                second_result = enricher.run(db, nipt=input_nipt, delay_seconds=0, force=True)
                profile = db.scalar(select(OpenCorporatesCompanyProfile))
                financial_rows = db.scalars(
                    select(OpenCorporatesFinancialYear).order_by(OpenCorporatesFinancialYear.year)
                ).all()

        assert profile is not None
        self.assertEqual(first_result["pages_found"], 1)
        self.assertEqual(first_result["financial_rows_upserted"], 2)
        self.assertEqual(first_result["requested_nipt"], nipt)
        self.assertEqual(second_result["financial_rows_upserted"], 2)
        self.assertEqual(http.calls, [_company_url(nipt), _company_url(nipt)])
        self.assertEqual(len(financial_rows), 2)
        self.assertEqual(profile.nipt, nipt)
        self.assertTrue(profile.has_financial_data)
        self.assertEqual(profile.parse_status, "ok")
        self.assertEqual(profile.financial_year_count, 2)
        self.assertEqual(str(financial_rows[0].revenue_amount), "79495669.00")
        self.assertEqual(str(financial_rows[1].revenue_amount), "81000000.00")
        self.assertEqual(str(financial_rows[0].profit_before_tax_amount), "1250000.50")

    def test_404_page_is_persisted_as_missing_without_financial_rows(self) -> None:
        nipt = "K12345678A"
        http = _FakeHttpClient(
            {
                _company_url(nipt): (404, "<html><body>Page not found</body></html>"),
            }
        )
        enricher = OpenCorporatesFinancialEnricher(http_client=http, sleeper=lambda _: None)

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = enricher.run(db, nipt=nipt, delay_seconds=0, force=True)
                profile = db.scalar(select(OpenCorporatesCompanyProfile))
                financial_rows = db.scalars(select(OpenCorporatesFinancialYear)).all()

        assert profile is not None
        self.assertEqual(http.calls, [_company_url(nipt)])
        self.assertEqual(result["http_requests_executed"], 1)
        self.assertEqual(result["pages_missing"], 1)
        self.assertEqual(result["financial_rows_upserted"], 0)
        self.assertFalse(profile.page_found)
        self.assertEqual(profile.parse_status, "missing_page")
        self.assertEqual(financial_rows, [])

    def test_server_errors_remain_retryable(self) -> None:
        nipt = "K12345678A"
        now = datetime(2026, 6, 19, 12, 0, 0)
        http = _FakeHttpClient({_company_url(nipt): (500, "<html><body>Server error</body></html>")})
        enricher = OpenCorporatesFinancialEnricher(
            http_client=http,
            sleeper=lambda _: None,
            now_factory=lambda: now,
        )

        with isolated_db_environment() as (_, session_factory, engine):
            Base.metadata.create_all(bind=engine)
            with session_factory() as db:
                result = enricher.run(db, nipt=nipt, delay_seconds=0, force=False)
                profile = db.scalar(select(OpenCorporatesCompanyProfile))
                retry_selection = select_opencorporates_financial_nipts(
                    db,
                    limit=1,
                    offset=0,
                    nipt=nipt,
                    only_shpk=True,
                    force=False,
                    stale_before=now - timedelta(days=30),
                )

        assert profile is not None
        self.assertEqual(http.calls, [_company_url(nipt)])
        self.assertEqual(result["http_errors"], 1)
        self.assertEqual(profile.parse_status, "http_error")
        self.assertIsNone(profile.page_found)
        self.assertEqual(retry_selection["selected_nipts"], [nipt])


if __name__ == "__main__":
    unittest.main()
