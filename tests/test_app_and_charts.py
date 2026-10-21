"""Testy modeli ORM, wykresów Plotly (charts.py), komponentów (utils.py) oraz data_provider.py."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from src.app.data_provider import (
    get_asset_geneartion_and_prices,
    get_data_for_bess,
    get_dates_of_summaries,
    get_energy_prices,
    get_energy_prices_and_forecasts,
    get_kse_contracting_status,
    get_min_max_date,
    get_news_articles,
    get_news_digest,
)

from energy_dash.core.db import Base
from src.app.components.charts import (
    _get_x_axis,
    get_background_colors,
    plot_price_indices_contracting_status_1h,
    plot_price_indices_contracting_status_15min,
    plot_strategy_schedule,
)
from src.app.components.utils import render_items
from src.models_db import energy, forecasts, news, renewables  # noqa: F401
from src.models_db.energy import EnergyPrice


class TestOrmModels:
    """Testy definicji tabel SQLAlchemy w src/models_db/."""

    def test_all_expected_tables_registered_in_metadata(self):
        expected_tables = {
            "energy_prices",
            "pse_forecasts",
            "pse_actuals",
            "v_energy_summary",
            "da_price_forecasts",
            "news_articles",
            "news_digests",
            "renewable_farms",
            "renewable_generation",
        }
        assert expected_tables.issubset(set(Base.metadata.tables.keys()))

    def test_energy_price_repr(self):
        dt = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
        ep = EnergyPrice(datetime_utc=dt, rce_pln_mwh=412.5)
        assert "412.5" in repr(ep)


class TestCharts:
    """Testy funkcji generujących wykresy Plotly w src/app/components/charts.py."""

    def test_get_background_colors(self):
        s = pd.Series([10.0, -5.0, 0.0, np.nan])
        colors = get_background_colors(s, pos_color="POS", neg_color="NEG")
        assert list(colors) == ["POS", "NEG", "rgba(0,0,0,0)", "rgba(0,0,0,0)"]

    def test_get_x_axis_prefers_datetime_columns_over_index(self):
        idx = pd.date_range("2026-10-20", periods=3, freq="1h", tz="Europe/Warsaw")
        df_idx = pd.DataFrame({"a": [1, 2, 3]}, index=idx)
        assert _get_x_axis(df_idx) is df_idx.index

        df_col = pd.DataFrame({"datetime_local": idx, "a": [1, 2, 3]})
        assert (_get_x_axis(df_col) == df_col["datetime_local"]).all()

    def test_plot_price_indices_15min_and_1h_with_confidence_intervals(self):
        idx = pd.date_range("2026-10-20", periods=4, freq="15min", tz="Europe/Warsaw")
        df = pd.DataFrame(
            {
                "fixing_1_pln_mwh": [400.0, 410.0, 420.0, 430.0],
                "fixing_2_pln_mwh": [405.0, 415.0, 425.0, 435.0],
                "cen_pln_mwh": [390.0, 400.0, 450.0, 460.0],
                "fixing_1_forecast_pln_mwh": [395.0, 405.0, 415.0, 425.0],
                "kse_contracting_status": [100.0, -50.0, 0.0, 20.0],
                "p05": [300.0] * 4,
                "p95": [500.0] * 4,
                "p10": [320.0] * 4,
                "p90": [480.0] * 4,
                "p25": [350.0] * 4,
                "p75": [450.0] * 4,
            },
            index=idx,
        )
        fig15 = plot_price_indices_contracting_status_15min(df)
        fig1h = plot_price_indices_contracting_status_1h(df)
        assert isinstance(fig15, go.Figure)
        assert isinstance(fig1h, go.Figure)
        # 1 bar + 3*2 (przedziały ufności) + 1 prognoza + 3 indeksy = 11 trace'ów
        assert len(fig15.data) == 11

    def test_plot_strategy_schedule_returns_two_row_subplot_figure(self):
        idx = pd.date_range("2026-10-20", periods=4, freq="1h", tz="Europe/Warsaw")
        sched_df = pd.DataFrame(
            {
                "charge_mw": [5.0, 5.0, 0.0, 0.0],
                "discharge_mw": [0.0, 0.0, 5.0, 5.0],
                "soc_mwh": [4.5, 9.0, 4.0, 0.0],
            },
            index=idx,
        )
        prices_df = pd.DataFrame(
            {
                "price_real": [200.0, 210.0, 600.0, 620.0],
                "price_forecast": [210.0, 220.0, 580.0, 600.0],
            },
            index=idx,
        )
        fig = plot_strategy_schedule(
            df=sched_df,
            prices_df=prices_df,
            revenue=3500.0,
            revenue_basis="real",
            strategy_name="Optymalizacja prognostyczna",
        )
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 5  # price_real, price_forecast, discharge, charge, soc


class TestComponentUtils:
    """Testy funkcji pomocniczych w src/app/components/utils.py."""

    def test_render_items_calls_info_when_horizon_empty(self):
        with patch("src.app.components.utils.st") as mock_st:
            render_items([{"horizon": "long"}], "short")
            mock_st.info.assert_called_once()
            mock_st.markdown.assert_not_called()

    def test_render_items_formats_markdown_with_icons_and_sources(self):
        items = [
            {
                "horizon": "short",
                "commodity": "power",
                "impact": "up",
                "summary": "Wzrost cen na RDN.",
                "sources": [{"id": 1, "source": "PAP", "url": "https://pap.pl/1"}],
            }
        ]
        with patch("src.app.components.utils.st") as mock_st:
            render_items(items, "short")
            mock_st.markdown.assert_called_once()
            arg = mock_st.markdown.call_args[0][0]
            assert "📈" in arg
            assert "**energia**" in arg
            assert "[PAP](https://pap.pl/1)" in arg


class TestDataProvider:
    """Testy funkcji pobierania danych z bazy w src/app/data_provider.py (z mockowanym SQL)."""

    def test_get_min_max_date_returns_none_when_table_empty(self):
        get_min_max_date.clear()
        empty_df = pd.DataFrame({"min_date": [None], "max_date": [None]})
        with patch("src.app.data_provider.pd.read_sql", return_value=empty_df):
            min_d, max_d = get_min_max_date("fixing_1_pln_mwh")
            assert min_d is None and max_d is None

    def test_get_min_max_date_converts_to_warsaw_tz(self):
        get_min_max_date.clear()
        raw_df = pd.DataFrame(
            {
                "min_date": [datetime(2026, 10, 1, 22, 0, tzinfo=UTC)],
                "max_date": [datetime(2026, 10, 20, 21, 45, tzinfo=UTC)],
            }
        )
        with patch("src.app.data_provider.pd.read_sql", return_value=raw_df):
            min_d, max_d = get_min_max_date("fixing_1_pln_mwh")
            assert min_d is not None and max_d is not None
            assert str(min_d.tzinfo) == "Europe/Warsaw"
            assert min_d.date() == date(2026, 10, 2)

    def test_get_energy_prices_converts_utc_to_local_index(self):
        get_energy_prices.clear()
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range(
                    "2026-10-19 22:00", periods=4, freq="15min", tz="UTC"
                ),
                "fixing_1_pln_mwh": [400.0, 405.0, 410.0, 415.0],
            }
        )
        with patch("src.app.data_provider.pd.read_sql", return_value=raw_df):
            df = get_energy_prices(
                pd.Timestamp("2026-10-19 22:00", tz="UTC"),
                pd.Timestamp("2026-10-19 23:00", tz="UTC"),
                columns=["fixing_1_pln_mwh"],
            )
            assert df.index.name == "datetime_local"
            assert str(df.index.tz) == "Europe/Warsaw"
            assert "datetime_utc" not in df.columns

    def test_get_kse_contracting_status_converts_utc_to_local_index(self):
        get_kse_contracting_status.clear()
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range(
                    "2026-10-19 22:00", periods=2, freq="15min", tz="UTC"
                ),
                "kse_contracting_status": [50.0, -30.0],
            }
        )
        with patch("src.app.data_provider.pd.read_sql", return_value=raw_df):
            df = get_kse_contracting_status(
                pd.Timestamp("2026-10-19 22:00", tz="UTC"),
                pd.Timestamp("2026-10-19 22:30", tz="UTC"),
            )
            assert str(df.index.tz) == "Europe/Warsaw"
            assert list(df["kse_contracting_status"]) == [50.0, -30.0]

    def test_get_asset_generation_and_prices_dropna(self):
        get_asset_geneartion_and_prices.clear()
        raw_df = pd.DataFrame(
            {
                "farm_id": [1, 1],
                "datetime_utc": pd.date_range("2026-10-19 22:00", periods=2, freq="1h", tz="UTC"),
                "generation_mwh": [5.0, np.nan],
                "generation_forecast_mwh": [4.8, 5.1],
                "fixing_1_pln_mwh": [400.0, 410.0],
                "fixing_2_pln_mwh": [405.0, 415.0],
                "cen_pln_mwh": [390.0, 420.0],
            }
        )
        with patch("src.app.data_provider.pd.read_sql", return_value=raw_df):
            df = get_asset_geneartion_and_prices(asset_id=1, dropna=True)
            assert len(df) == 1
            assert str(df.index.tz) == "Europe/Warsaw"

    def test_get_data_for_bess_keeps_utc_index(self):
        get_data_for_bess.clear()
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range("2026-10-19 22:00", periods=24, freq="1h"),
                "forecast_pln_mwh": [400.0] * 24,
                "fixing_1_pln_mwh": [410.0] * 24,
            }
        )
        with patch("src.app.data_provider.pd.read_sql", return_value=raw_df):
            df = get_data_for_bess("2026-10-19T22:00:00Z", "2026-10-20T22:00:00Z", "3")
            assert str(df.index.tz) == "UTC"
            assert len(df) == 24

    def test_get_energy_prices_and_forecasts_sets_warsaw_index(self):
        get_energy_prices_and_forecasts.clear()
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range(
                    "2026-10-19 22:00", periods=4, freq="15min", tz="UTC"
                ),
                "datetime_local": pd.date_range("2026-10-20 00:00", periods=4, freq="15min"),
                "model_version": ["3"] * 4,
                "fixing_1_forecast_pln_mwh": [400.0] * 4,
                "fixing_1_pln_mwh": [410.0] * 4,
            }
        )
        with patch("src.app.data_provider.pd.read_sql", return_value=raw_df):
            df = get_energy_prices_and_forecasts(
                pd.Timestamp("2026-10-19 22:00", tz="UTC"),
                pd.Timestamp("2026-10-19 23:00", tz="UTC"),
            )
            assert str(df.index.tz) == "Europe/Warsaw"
            assert "datetime_utc" not in df.columns

    def test_get_news_functions_mocked_session(self):
        get_news_articles.clear()
        get_news_digest.clear()
        get_dates_of_summaries.clear()

        fake_art = SimpleNamespace(
            id=1,
            topic="power",
            title="Test",
            source="PAP",
            url="https://gnews/1",
            real_url="https://pap.pl/1",
            published_utc=datetime(2026, 10, 20, 6, 0, tzinfo=UTC),
        )
        fake_dig = SimpleNamespace(
            items=[{"horizon": "short"}],
            generated_utc=datetime(2026, 10, 20, 7, 5, tzinfo=UTC),
            model="ollama/gemma4:e4b",
            n_articles=5,
        )

        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
            fake_art
        ]
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = fake_dig
        mock_session.query.return_value.order_by.return_value.all.return_value = [
            (date(2026, 10, 20),)
        ]

        with patch("src.app.data_provider.SessionLocal", return_value=mock_session):
            arts_df = get_news_articles(date(2026, 10, 20))
            assert len(arts_df) == 1
            assert arts_df.iloc[0]["url"] == "https://pap.pl/1"

            dig = get_news_digest(date(2026, 10, 20))
            assert dig is not None
            assert dig["n_articles"] == 5

            dates = get_dates_of_summaries()
            assert dates == [date(2026, 10, 20)]
