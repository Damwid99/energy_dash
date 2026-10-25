"""Testy ekstraktorów i transformacji ETL (TGE, PSE, RSS, News Digest, scheduler)."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import requests

from energy_dash.core.http import build_retrying_session
from energy_dash.features.market_prices.etl_pse import (
    fetch_and_save_cen,
    fetch_and_save_rce,
)
from energy_dash.features.market_prices.etl_tge import (
    _expected_quarters,
    _num,
    earliest_delivery_date,
    fetch_and_save_tge,
    latest_delivery_date,
    parse_tge_day,
    save_tge_day,
)
from energy_dash.features.news.digest import ensure_body, generate_digest
from energy_dash.features.news.etl_rss import _feed_url, fetch_and_save_news
from energy_dash.features.news.schemas import Digest, DigestItem, SelectedArticle, Selection
from energy_dash.features.power_system.etl import (
    _fetch_kse_demand_hourly,
    fetch_and_save_oze,
    fetch_and_save_oze_actuals,
)

WARSAW = ZoneInfo("Europe/Warsaw")


def test_build_retrying_session_returns_requests_session():
    """Weryfikuje tworzenie sesji HTTP z adapterem retry."""
    s = build_retrying_session(total=2, backoff_factor=0.5)
    assert isinstance(s, requests.Session)


def _build_tge_html(
    delivery_date: date,
    n_quarters: int = 96,
    header_override: list[str] | None = None,
) -> bytes:
    """Buduje syntetyczny HTML tabeli #rdn zgodny ze strukturą TGE."""
    headers = header_override or [
        "Czas",
        "Instrument",
        "Kurs [PLN/MWh]",
        "Wolumen [MW]",
        "Col4",
        "Col5",
        "Col6",
        "Kurs jednolity [PLN/MWh]",
        "Wolumen [MW]",
        "Col9",
        "Col10",
        "Col11",
        "Col12",
        "Col13",
        "Col14",
        "Col15",
        "Col16",
    ]
    ths = "".join(f"<th>{h}</th>" for h in headers)
    rows_html = []
    for i in range(n_quarters):
        row_cells = [f"{delivery_date.isoformat()}_Q00:15", "RDN"] + [""] * 15
        row_cells[2] = f"{400 + i},50"
        row_cells[3] = "120,0"
        row_cells[7] = f"{410 + i},25"
        row_cells[8] = "80,5"
        tds = "".join(f"<td>{c}</td>" for c in row_cells)
        rows_html.append(f"<tr>{tds}</tr>")

    body = "".join(rows_html)
    html = f"""
    <html><body>
      <table id="rdn">
        <thead>
          <tr><th colspan="17">Nagłówek główny</th></tr>
          <tr>{ths}</tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </body></html>
    """
    return html.encode("utf-8")


class TestTgeApi:
    """Testy parsera i zapisu danych TGE."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1 116,80", 1116.8),
            ("450,00", 450.0),
            ("-", None),
            ("  ", None),
            ("-50,25", -50.25),
        ],
    )
    def test_num_conversion(self, raw: str, expected: float | None):
        assert _num(raw) == expected

    def test_latest_and_earliest_delivery_date(self):
        before_14 = datetime(2026, 10, 20, 13, 30, tzinfo=WARSAW)
        after_14 = datetime(2026, 10, 20, 14, 5, tzinfo=WARSAW)
        assert latest_delivery_date(before_14) == date(2026, 10, 20)
        assert latest_delivery_date(after_14) == date(2026, 10, 21)
        assert earliest_delivery_date(before_14) == date(2026, 10, 20) - (
            date(2026, 10, 20) - date(2026, 8, 22)
        )

    def test_expected_quarters_dst_and_normal(self):
        assert _expected_quarters(date(2026, 10, 20)) == 96
        assert _expected_quarters(date(2026, 3, 29)) == 92  # zmiana czasu na letni (23h)
        assert _expected_quarters(date(2026, 10, 25)) == 100  # zmiana czasu na zimowy (25h)

    def test_parse_tge_day_valid_96_quarters(self):
        d = date(2026, 10, 20)
        html = _build_tge_html(d, n_quarters=96)
        rows = parse_tge_day(html, d)
        assert len(rows) == 96
        assert rows[0]["fixing_1_pln_mwh"] == pytest.approx(400.50)
        assert rows[0]["fixing_2_pln_mwh"] == pytest.approx(410.25)
        assert rows[0]["datetime_utc"] == datetime(2026, 10, 19, 22, 0, tzinfo=UTC)

    def test_parse_tge_day_raises_on_missing_table(self):
        with pytest.raises(ValueError, match="brak tabeli #rdn"):
            parse_tge_day(b"<html><body>Brak</body></html>", date(2026, 10, 20))

    def test_parse_tge_day_raises_on_changed_headers(self):
        d = date(2026, 10, 20)
        bad_headers = ["Col"] * 17
        html = _build_tge_html(d, n_quarters=96, header_override=bad_headers)
        with pytest.raises(ValueError, match="zmienił się układ tabeli TGE"):
            parse_tge_day(html, d)

    def test_parse_tge_day_raises_on_wrong_quarter_count(self):
        d = date(2026, 10, 20)
        html = _build_tge_html(d, n_quarters=50)
        with pytest.raises(ValueError, match="oczekiwano 96"):
            parse_tge_day(html, d)

    def test_save_tge_day_inserts_and_updates_preserving_rce(self):
        dt1 = datetime(2026, 10, 19, 22, 0, tzinfo=UTC)
        dt2 = datetime(2026, 10, 19, 22, 15, tzinfo=UTC)
        existing_rec = SimpleNamespace(
            datetime_utc=dt1,
            fixing_1_pln_mwh=100.0,
            fixing_1_volume=10.0,
            fixing_2_pln_mwh=None,
            fixing_2_volume=None,
            rce_pln_mwh=555.0,
        )
        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.all.return_value = [existing_rec]

        rows = [
            {
                "datetime_utc": dt1,
                "fixing_1_pln_mwh": 350.0,
                "fixing_1_volume": 50.0,
                "fixing_2_pln_mwh": 360.0,
                "fixing_2_volume": 40.0,
            },
            {
                "datetime_utc": dt2,
                "fixing_1_pln_mwh": 355.0,
                "fixing_1_volume": 52.0,
                "fixing_2_pln_mwh": 365.0,
                "fixing_2_volume": 42.0,
            },
        ]
        n = save_tge_day(fake_session, rows)
        assert n == 2
        assert existing_rec.fixing_1_pln_mwh == 350.0
        assert existing_rec.fixing_2_pln_mwh == 360.0
        assert existing_rec.rce_pln_mwh == 555.0  # nienaruszone!
        assert fake_session.add.call_count == 1

    def test_fetch_and_save_tge_end_to_end_mocked(self):
        d = date(2026, 10, 20)
        html = _build_tge_html(d, n_quarters=96)
        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.all.return_value = []

        with (
            patch(
                "energy_dash.features.market_prices.etl_tge.latest_delivery_date",
                return_value=d,
            ),
            patch(
                "energy_dash.features.market_prices.etl_tge.earliest_delivery_date",
                return_value=date(2026, 9, 1),
            ),
            patch("energy_dash.features.market_prices.etl_tge._fetch_html", return_value=html),
            patch(
                "energy_dash.features.market_prices.etl_tge.SessionLocal",
                return_value=fake_session,
            ),
            patch("energy_dash.features.market_prices.etl_tge.time.sleep"),
        ):
            failed = fetch_and_save_tge(start_date="2026-10-20", end_date="2026-10-20")
            assert failed == []
            assert fake_session.commit.call_count == 1

    def test_parse_tge_day_dst_25h_with_a_labels(self):
        """Weryfikuje parsowanie doby jesiennej (25h = 100 kwadransów) z etykietami Q01a/Q02a."""
        d = date(2026, 10, 25)
        rows_html = []
        # Godziny H01, H02 (kwadranse standardowe)
        for h in [0, 1]:
            for q in [15, 30, 45]:
                rows_html.append(
                    f"<tr><td>{d.isoformat()}_Q{h:02d}:{q:02d}</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                    + "<td></td>" * 3
                    + "<td>410,0</td><td>100,0</td>"
                    + "<td></td>" * 9
                    + "</tr>"
                )
            rows_html.append(
                f"<tr><td>{d.isoformat()}_Q{h + 1:02d}:00</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                + "<td></td>" * 3
                + "<td>410,0</td><td>100,0</td>"
                + "<td></td>" * 9
                + "</tr>"
            )
        # Godzina H02a (dodatkowa godzina ze zmianą czasu: Q01a:15..Q02a:00)
        for q in [15, 30, 45]:
            rows_html.append(
                f"<tr><td>{d.isoformat()}_Q01a:{q:02d}</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                + "<td></td>" * 3
                + "<td>410,0</td><td>100,0</td>"
                + "<td></td>" * 9
                + "</tr>"
            )
        rows_html.append(
            f"<tr><td>{d.isoformat()}_Q02a:00</td><td>RDN</td><td>400,0</td><td>100,0</td>"
            + "<td></td>" * 3
            + "<td>410,0</td><td>100,0</td>"
            + "<td></td>" * 9
            + "</tr>"
        )
        # Pozostałe godziny H03..H24 (88 kwadransów)
        for h in range(2, 24):
            for q in [15, 30, 45]:
                rows_html.append(
                    f"<tr><td>{d.isoformat()}_Q{h:02d}:{q:02d}</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                    + "<td></td>" * 3
                    + "<td>410,0</td><td>100,0</td>"
                    + "<td></td>" * 9
                    + "</tr>"
                )
            rows_html.append(
                f"<tr><td>{d.isoformat()}_Q{h + 1:02d}:00</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                + "<td></td>" * 3
                + "<td>410,0</td><td>100,0</td>"
                + "<td></td>" * 9
                + "</tr>"
            )

        headers = [
            "Czas",
            "Instrument",
            "Kurs [PLN/MWh]",
            "Wolumen [MW]",
            "Col4",
            "Col5",
            "Col6",
            "Kurs jednolity [PLN/MWh]",
            "Wolumen [MW]",
            "Col9",
            "Col10",
            "Col11",
            "Col12",
            "Col13",
            "Col14",
            "Col15",
            "Col16",
        ]
        ths = "".join(f"<th>{h}</th>" for h in headers)
        html = f"<html><body><table id='rdn'><thead><tr><th colspan='17'>Nagłówek</th></tr><tr>{ths}</tr></thead><tbody>{''.join(rows_html)}</tbody></table></body></html>".encode()

        rows = parse_tge_day(html, d)
        assert len(rows) == 100
        assert rows[0]["datetime_utc"] == datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
        assert rows[-1]["datetime_utc"] == datetime(2026, 10, 25, 22, 45, tzinfo=UTC)

    def test_parse_tge_day_dst_23h_spring(self):
        """Weryfikuje parsowanie doby wiosennej (23h = 92 kwadranse, brak godziny 02:00)."""
        d = date(2026, 3, 29)
        rows_html = []
        # 23 godziny: godziny 00..01, pomijamy 02, godziny 03..23
        for h in [0, 1] + list(range(3, 24)):
            for q in [15, 30, 45]:
                rows_html.append(
                    f"<tr><td>{d.isoformat()}_Q{h:02d}:{q:02d}</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                    + "<td></td>" * 3
                    + "<td>410,0</td><td>100,0</td>"
                    + "<td></td>" * 9
                    + "</tr>"
                )
            rows_html.append(
                f"<tr><td>{d.isoformat()}_Q{h + 1:02d}:00</td><td>RDN</td><td>400,0</td><td>100,0</td>"
                + "<td></td>" * 3
                + "<td>410,0</td><td>100,0</td>"
                + "<td></td>" * 9
                + "</tr>"
            )

        headers = [
            "Czas",
            "Instrument",
            "Kurs [PLN/MWh]",
            "Wolumen [MW]",
            "Col4",
            "Col5",
            "Col6",
            "Kurs jednolity [PLN/MWh]",
            "Wolumen [MW]",
            "Col9",
            "Col10",
            "Col11",
            "Col12",
            "Col13",
            "Col14",
            "Col15",
            "Col16",
        ]
        ths = "".join(f"<th>{h}</th>" for h in headers)
        html = f"<html><body><table id='rdn'><thead><tr><th colspan='17'>Nagłówek</th></tr><tr>{ths}</tr></thead><tbody>{''.join(rows_html)}</tbody></table></body></html>".encode()

        rows = parse_tge_day(html, d)
        assert len(rows) == 92
        assert rows[0]["datetime_utc"] == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
        assert rows[-1]["datetime_utc"] == datetime(2026, 3, 29, 21, 45, tzinfo=UTC)


class TestPseApi:
    """Testy pobierania danych RCE, CEN, OZE Actuals oraz OZE Forecasts z PSE."""

    def test_fetch_kse_demand_hourly_aggregates_only_complete_hours(self):
        payload = {
            "value": [
                {"dtime_utc": "2026-10-20 00:15:00", "load_fcst": 18000},
                {"dtime_utc": "2026-10-20 00:30:00", "load_fcst": 18200},
                {"dtime_utc": "2026-10-20 00:45:00", "load_fcst": 18400},
                {"dtime_utc": "2026-10-20 01:00:00", "load_fcst": 18600},
                {"dtime_utc": "2026-10-20 01:15:00", "load_fcst": 19000},
                {"dtime_utc": "2026-10-20 01:30:00", "load_fcst": 19200},
            ]
        }
        fake_http = MagicMock()
        fake_http.get.return_value.json.return_value = payload

        res = _fetch_kse_demand_hourly(fake_http, "2026-10-20")
        assert len(res) == 1
        assert res[datetime(2026, 10, 20, 0, 0, tzinfo=UTC)] == pytest.approx(18300.0)

    def test_fetch_and_save_rce_shifts_dtime_utc_by_15_minutes(self):
        fake_http = MagicMock()
        fake_http.get.return_value.json.return_value = {
            "value": [{"dtime_utc": "2026-10-20 00:15:00", "rce_pln": 420.5}]
        }

        with (
            patch(
                "energy_dash.features.market_prices.etl_pse.build_retrying_session",
                return_value=fake_http,
            ),
            patch(
                "energy_dash.features.market_prices.etl_pse.postgres_upsert",
                return_value=1,
            ) as mock_upsert,
            patch("energy_dash.features.market_prices.etl_pse.time.sleep"),
        ):
            fetch_and_save_rce(start_date="2026-10-20", end_date="2026-10-20")
            mock_upsert.assert_called_once()
            records = mock_upsert.call_args.kwargs["records"]
            assert len(records) == 1
            assert records[0]["datetime_utc"] == datetime(2026, 10, 20, 0, 0, tzinfo=UTC)
            assert records[0]["rce_pln_mwh"] == pytest.approx(420.5)

    def test_fetch_and_save_cen_parses_cen_cost_and_contracting_status(self):
        fake_http = MagicMock()
        fake_http.get.return_value.json.return_value = {
            "value": [
                {
                    "dtime_utc": "2026-10-20 01:00:00",
                    "cen_cost": 512.0,
                    "imb_energy": -145.2,
                }
            ]
        }

        with (
            patch(
                "energy_dash.features.market_prices.etl_pse.build_retrying_session",
                return_value=fake_http,
            ),
            patch(
                "energy_dash.features.market_prices.etl_pse.postgres_upsert",
                return_value=1,
            ) as mock_upsert,
            patch("energy_dash.features.market_prices.etl_pse.time.sleep"),
        ):
            fetch_and_save_cen(start_date="2026-10-20", end_date="2026-10-20")
            mock_upsert.assert_called_once()
            records = mock_upsert.call_args.kwargs["records"]
            assert len(records) == 1
            assert records[0]["datetime_utc"] == datetime(2026, 10, 20, 0, 45, tzinfo=UTC)
            assert records[0]["cen_pln_mwh"] == pytest.approx(512.0)
            assert records[0]["kse_contracting_status"] == pytest.approx(-145.2)

    def test_fetch_and_save_oze_actuals_computes_exchange_and_resload(self):
        fake_http = MagicMock()
        fake_http.get.return_value.json.return_value = {
            "value": [
                {
                    "dtime_utc": "2026-10-20 12:15:00",
                    "pv": 3000.0,
                    "wi": 2000.0,
                    "demand": 20000.0,
                    "swm_p": 500.0,
                    "swm_np": -100.0,
                }
            ]
        }

        with (
            patch(
                "energy_dash.features.power_system.etl.build_retrying_session",
                return_value=fake_http,
            ),
            patch(
                "energy_dash.features.power_system.etl.postgres_upsert",
                return_value=1,
            ) as mock_upsert,
            patch("energy_dash.features.power_system.etl.time.sleep"),
        ):
            fetch_and_save_oze_actuals(start_date="2026-10-20", end_date="2026-10-20")
            mock_upsert.assert_called_once()
            records = mock_upsert.call_args.kwargs["records"]
            assert len(records) == 1
            assert records[0]["datetime_utc"] == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
            assert records[0]["exchange_actual_pse"] == pytest.approx(400.0)
            assert records[0]["resload_actual_pse"] == pytest.approx(15000.0)

    def test_fetch_and_save_oze_forecasts_joins_hourly_demand(self):
        fake_http = MagicMock()
        fake_http.get.return_value.json.return_value = {
            "value": [
                {
                    "plan_dtime_utc": "2026-10-20 13:00:00",  # koniec godziny -> 12:00 UTC
                    "publication_ts_utc": "2026-10-19 10:00:00.000",
                    "fcst_pv_tot_gen": 2500.0,
                    "fcst_wi_tot_gen": 1500.0,
                    "planned_exchange": -200.0,
                }
            ]
        }
        demand_map = {datetime(2026, 10, 20, 12, 0, tzinfo=UTC): 19000.0}

        with (
            patch(
                "energy_dash.features.power_system.etl.build_retrying_session",
                return_value=fake_http,
            ),
            patch(
                "energy_dash.features.power_system.etl._fetch_kse_demand_hourly",
                return_value=demand_map,
            ),
            patch(
                "energy_dash.features.power_system.etl.postgres_upsert",
                return_value=1,
            ) as mock_upsert,
            patch("energy_dash.features.power_system.etl.time.sleep"),
        ):
            fetch_and_save_oze(start_date="2026-10-20", end_date="2026-10-20")
            mock_upsert.assert_called_once()
            records = mock_upsert.call_args.kwargs["records"]
            assert len(records) == 1
            assert records[0]["issue_datetime_utc"] == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
            assert records[0]["demand_fcst_pse"] == pytest.approx(19000.0)
            assert records[0]["resload_fcst_pse"] == pytest.approx(15000.0)


class TestNewsRssAndDigest:
    """Testy pobierania RSS i generowania podsumowania newsów."""

    def test_feed_url_builds_google_news_search_url(self):
        url = _feed_url("rynek energii", "pl", "PL", "PL:pl", days_back=2)
        assert "https://news.google.com/rss/search?" in url
        assert "when%3A2d" in url
        assert "hl=pl&gl=PL&ceid=PL:pl" in url

    def test_fetch_and_save_news_strips_source_suffix_and_deduplicates(self):
        class _FeedEntry(dict):
            __getattr__ = dict.get

        entry = _FeedEntry(
            {
                "link": "https://news.google.com/articles/abc",
                "title": "Rekordowa generacja wiatrowa w Polsce - BiznesAlert",
                "published_parsed": (2026, 10, 20, 8, 30, 0, 1, 293, 0),
                "source": {"title": "BiznesAlert"},
            }
        )
        fake_feed = SimpleNamespace(entries=[entry, entry])
        fake_session = MagicMock()
        fake_session.execute.return_value.fetchall.return_value = [(1,)]

        with (
            patch("energy_dash.features.news.etl_rss.feedparser.parse", return_value=fake_feed),
            patch("energy_dash.features.news.etl_rss.SessionLocal", return_value=fake_session),
        ):
            fetch_and_save_news(days_back=2)
            assert fake_session.execute.called
            assert fake_session.commit.called

    def test_ensure_body_skips_when_body_already_present(self):
        fake_session = MagicMock()
        art = SimpleNamespace(id=1, url="https://example.com", real_url=None, body="Już pobrane")
        ensure_body(fake_session, art)  # type: ignore[arg-type]
        fake_session.commit.assert_not_called()

    def test_ensure_body_fetches_and_extracts_article(self):
        fake_session = MagicMock()
        art = SimpleNamespace(id=1, url="https://news.google.com/xyz", real_url=None, body=None)
        with (
            patch(
                "energy_dash.features.news.digest.gnewsdecoder",
                return_value={"status": True, "decoded_url": "https://portal.pl/art1"},
            ),
            patch(
                "energy_dash.features.news.digest.trafilatura.fetch_url",
                return_value="<html>ok</html>",
            ),
            patch(
                "energy_dash.features.news.digest.trafilatura.extract",
                return_value="Treść artykułu",
            ),
        ):
            ensure_body(fake_session, art)  # type: ignore[arg-type]
            assert art.real_url == "https://portal.pl/art1"
            assert art.body == "Treść artykułu"
            fake_session.commit.assert_called_once()

    def test_generate_digest_full_flow_mocked(self):
        art = SimpleNamespace(
            id=10,
            url="https://news.google.com/10",
            real_url="https://portal.pl/10",
            title="Ceny gazu spadają",
            source="Portal",
            topic="gas",
            published_utc=datetime(2026, 10, 20, 6, 0, tzinfo=UTC),
            body="Pełny tekst artykułu o spadku cen gazu TTF.",
        )
        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            art
        ]
        sel_resp = Selection(selected=[SelectedArticle(id=10, horizon="short")])
        dig_resp = Digest(
            items=[
                DigestItem(
                    horizon="short",
                    commodity="gas",
                    impact="down",
                    summary="Spadek cen gazu TTF obniża koszty wytwarzania.",
                    source_ids=[10],
                )
            ]
        )

        with (
            patch("energy_dash.features.news.digest.digest_exists", return_value=False),
            patch("energy_dash.features.news.digest.SessionLocal", return_value=fake_session),
            patch(
                "energy_dash.features.news.digest.ask_structured",
                side_effect=[sel_resp, dig_resp],
            ),
        ):
            generate_digest(force=False)
            assert fake_session.add.called
            added_digest = fake_session.add.call_args[0][0]
            assert added_digest.n_articles == 1
            assert len(added_digest.items) == 1
            assert added_digest.items[0]["sources"][0]["id"] == 10


class TestRunEtlTasks:
    """Testy funkcji zadań harmonogramu w energy_dash.etl.scheduler."""

    def test_task_cen_calls_fetch_and_save_cen(self):
        from energy_dash.etl.scheduler import task_cen

        with patch("energy_dash.etl.scheduler.fetch_and_save_cen") as mock_cen:
            task_cen()
            mock_cen.assert_called_once_with(days_back=2)

    def test_task_daily_market_data_calls_all_extractors_and_evaluation(self):
        from energy_dash.etl.scheduler import task_daily_market_data

        with (
            patch("energy_dash.etl.scheduler.fetch_and_save_rce") as m_rce,
            patch("energy_dash.etl.scheduler.fetch_and_save_tge") as m_tge,
            patch("energy_dash.etl.scheduler.fetch_and_save_oze_actuals") as m_oze_act,
            patch("energy_dash.etl.scheduler.task_evaluate_forecasts") as m_eval,
        ):
            task_daily_market_data()
            m_rce.assert_called_once_with(days_back=5)
            m_tge.assert_called_once_with(days_back=3)
            m_oze_act.assert_called_once_with(days_back=5)
            m_eval.assert_called_once_with(days_back=4)

    def test_task_news_daily_skips_if_digest_already_exists(self):
        from energy_dash.etl.scheduler import task_news_daily

        with (
            patch("energy_dash.etl.scheduler.digest_exists", return_value=True),
            patch("energy_dash.etl.scheduler.fetch_and_save_news") as m_news,
            patch("energy_dash.etl.scheduler.generate_digest") as m_dig,
        ):
            task_news_daily()
            m_news.assert_not_called()
            m_dig.assert_not_called()

    def test_task_daily_forecast_has_valid_import(self):
        """Sprawdza, czy task_daily_forecast() potrafi zaimportować run_daily_forecast bez błędu."""
        with patch("energy_dash.features.forecasting.predictor.run_daily_forecast") as mock_run:
            from energy_dash.etl.scheduler import task_daily_forecast

            task_daily_forecast()
            assert mock_run.called

    def test_build_scheduler_registers_core_jobs(self):
        """Sprawdza, czy build_scheduler() poprawnie rejestruje zadania cykliczne."""
        from energy_dash.etl.scheduler import build_scheduler

        sched = build_scheduler()
        job_ids = {job.id for job in sched.get_jobs()}
        assert {
            "cen_peak",
            "daily_forecast",
            "cen_offpeak",
            "daily_rce_tge",
            "news_daily",
        }.issubset(job_ids)
