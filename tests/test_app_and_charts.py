"""Testy modeli ORM, wykresów Plotly, komponentów UI oraz warstwy zapytań (queries.py)."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import energy_dash.db_models  # noqa: F401
from energy_dash.core.db import Base
from energy_dash.features.assets.queries import (
    get_asset_geneartion_and_prices,
    get_assets_capacity_factors,
    get_assets_metadata,
)
from energy_dash.features.bess.charts import plot_strategy_schedule
from energy_dash.features.bess.queries import get_data_for_bess
from energy_dash.features.forecasting.queries import get_energy_prices_and_forecasts
from energy_dash.features.market_prices.charts import (
    _get_x_axis,
    get_background_colors,
    plot_price_indices_contracting_status_1h,
    plot_price_indices_contracting_status_15min,
)
from energy_dash.features.market_prices.models import EnergyPrice
from energy_dash.features.market_prices.queries import (
    get_energy_prices,
    get_kse_contracting_status,
    get_min_max_date,
)
from energy_dash.features.news.queries import (
    get_dates_of_summaries,
    get_news_articles,
    get_news_digest,
)
from energy_dash.features.news.ui import render_items


class TestOrmModels:
    """Testy definicji tabel SQLAlchemy rejestrowanych przez energy_dash.db_models."""

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
    """Testy funkcji generujących wykresy Plotly w market_prices/charts.py oraz bess/charts.py."""

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
        assert len(fig.data) == 5


class TestComponentUtils:
    """Testy funkcji pomocniczych w energy_dash.features.news.ui."""

    def test_render_items_calls_info_when_horizon_empty(self):
        with patch("energy_dash.features.news.ui.st") as mock_st:
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
        with patch("energy_dash.features.news.ui.st") as mock_st:
            render_items(items, "short")
            mock_st.markdown.assert_called_once()
            arg = mock_st.markdown.call_args[0][0]
            assert "📈" in arg
            assert "**energia**" in arg
            assert "[PAP](https://pap.pl/1)" in arg


class TestFeatureQueries:
    """Testy funkcji pobierania danych w features/*/queries.py (z mockowanym SQL)."""

    def test_get_min_max_date_returns_none_when_table_empty(self):
        empty_df = pd.DataFrame({"min_date": [None], "max_date": [None]})
        with patch("energy_dash.features.market_prices.queries.pd.read_sql", return_value=empty_df):
            min_d, max_d = get_min_max_date("fixing_1_pln_mwh")
            assert min_d is None and max_d is None

    def test_get_min_max_date_converts_to_warsaw_tz(self):
        raw_df = pd.DataFrame(
            {
                "min_date": [datetime(2026, 10, 1, 22, 0, tzinfo=UTC)],
                "max_date": [datetime(2026, 10, 20, 21, 45, tzinfo=UTC)],
            }
        )
        with patch("energy_dash.features.market_prices.queries.pd.read_sql", return_value=raw_df):
            min_d, max_d = get_min_max_date("fixing_1_pln_mwh")
            assert min_d is not None and max_d is not None
            assert str(min_d.tzinfo) == "Europe/Warsaw"
            assert min_d.date() == date(2026, 10, 2)

    def test_get_energy_prices_converts_utc_to_local_index(self):
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range(
                    "2026-10-19 22:00", periods=4, freq="15min", tz="UTC"
                ),
                "fixing_1_pln_mwh": [400.0, 405.0, 410.0, 415.0],
            }
        )
        with patch("energy_dash.features.market_prices.queries.pd.read_sql", return_value=raw_df):
            df = get_energy_prices(
                pd.Timestamp("2026-10-19 22:00", tz="UTC"),
                pd.Timestamp("2026-10-19 23:00", tz="UTC"),
                columns=["fixing_1_pln_mwh"],
            )
            assert df.index.name == "datetime_local"
            assert str(df.index.tz) == "Europe/Warsaw"
            assert "datetime_utc" not in df.columns

    def test_get_kse_contracting_status_converts_utc_to_local_index(self):
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range(
                    "2026-10-19 22:00", periods=2, freq="15min", tz="UTC"
                ),
                "kse_contracting_status": [50.0, -30.0],
            }
        )
        with patch("energy_dash.features.market_prices.queries.pd.read_sql", return_value=raw_df):
            df = get_kse_contracting_status(
                pd.Timestamp("2026-10-19 22:00", tz="UTC"),
                pd.Timestamp("2026-10-19 22:30", tz="UTC"),
            )
            assert str(df.index.tz) == "Europe/Warsaw"
            assert list(df["kse_contracting_status"]) == [50.0, -30.0]

    def test_get_assets_metadata_and_capacity_factors(self):
        meta_df = pd.DataFrame({"id": [1], "code": ["wind_pomorze"], "capacity_mw": [50.0]})
        cf_df = pd.DataFrame({"farm_id": [1], "capacity_factor": [0.35]})
        with patch("energy_dash.features.assets.queries.pd.read_sql", return_value=meta_df):
            assert len(get_assets_metadata()) == 1
        with patch("energy_dash.features.assets.queries.pd.read_sql", return_value=cf_df):
            assert get_assets_capacity_factors().iloc[0]["capacity_factor"] == 0.35

    def test_get_asset_generation_and_prices_dropna(self):
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
        with patch("energy_dash.features.assets.queries.pd.read_sql", return_value=raw_df):
            df = get_asset_geneartion_and_prices(asset_id=1, dropna=True)
            assert len(df) == 1
            assert str(df.index.tz) == "Europe/Warsaw"

    def test_get_data_for_bess_keeps_utc_index(self):
        raw_df = pd.DataFrame(
            {
                "datetime_utc": pd.date_range("2026-10-19 22:00", periods=24, freq="1h"),
                "forecast_pln_mwh": [400.0] * 24,
                "fixing_1_pln_mwh": [410.0] * 24,
            }
        )
        with patch("energy_dash.features.bess.queries.pd.read_sql", return_value=raw_df):
            df = get_data_for_bess("2026-10-19T22:00:00Z", "2026-10-20T22:00:00Z", "3")
            assert str(df.index.tz) == "UTC"
            assert len(df) == 24

    def test_get_energy_prices_and_forecasts_sets_warsaw_index(self):
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
        with patch("energy_dash.features.forecasting.queries.pd.read_sql", return_value=raw_df):
            df = get_energy_prices_and_forecasts(
                pd.Timestamp("2026-10-19 22:00", tz="UTC"),
                pd.Timestamp("2026-10-19 23:00", tz="UTC"),
            )
            assert str(df.index.tz) == "Europe/Warsaw"
            assert "datetime_utc" not in df.columns

    def test_get_news_functions_mocked_session(self):
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

        with patch("energy_dash.features.news.queries.SessionLocal", return_value=mock_session):
            arts_df = get_news_articles(date(2026, 10, 20))
            assert len(arts_df) == 1
            assert arts_df.iloc[0]["url"] == "https://pap.pl/1"

            dig = get_news_digest(date(2026, 10, 20))
            assert dig is not None
            assert dig["n_articles"] == 5

            dates = get_dates_of_summaries()
            assert dates == [date(2026, 10, 20)]

    def test_charts_dst_transition_25h_autumn(self):
        """Weryfikuje unikalność etykiet i brak schodków pionowych na wykresach w dobie 25h."""
        idx_25h = pd.date_range("2026-10-24 22:00", periods=25, freq="1h", tz="UTC").tz_convert(
            "Europe/Warsaw"
        )
        df_1h = pd.DataFrame(
            {
                "fixing_1_pln_mwh": [380.0] * 25,
                "fixing_2_pln_mwh": [370.0] * 25,
                "cen_pln_mwh": [350.0] * 25,
                "fixing_1_forecast_pln_mwh": [400.0] * 25,
                "kse_contracting_status": [0.0] * 25,
            },
            index=idx_25h,
        )
        fig_1h = plot_price_indices_contracting_status_1h(df_1h)
        x_cats = fig_1h.data[0].x
        assert len(x_cats) == 25
        assert len(set(x_cats)) == 25, "Wszystkie kategorie X muszą być unikalne!"
        assert x_cats[2] == "02:00"
        assert x_cats[3] == "02:00a"
        assert x_cats[4] == "03:00"

    def test_charts_dst_transition_23h_spring(self):
        """Weryfikuje poprawność wykresów w dobie wiosennej (23h) z pominięciem godziny 02:00."""
        idx_23h = pd.date_range("2026-03-28 23:00", periods=23, freq="1h", tz="UTC").tz_convert(
            "Europe/Warsaw"
        )
        df_1h = pd.DataFrame(
            {
                "fixing_1_pln_mwh": [380.0] * 23,
                "fixing_2_pln_mwh": [370.0] * 23,
                "cen_pln_mwh": [350.0] * 23,
                "fixing_1_forecast_pln_mwh": [400.0] * 23,
                "kse_contracting_status": [0.0] * 23,
            },
            index=idx_23h,
        )
        fig_1h = plot_price_indices_contracting_status_1h(df_1h)
        x_cats = fig_1h.data[0].x
        assert len(x_cats) == 23
        assert len(set(x_cats)) == 23
        assert x_cats[1] == "01:00"
        assert x_cats[2] == "03:00"
        assert "02:00" not in x_cats

    def test_charts_gaps_in_data_do_not_shrink_axis(self):
        """Weryfikuje, że brakujące godziny w danych nie ściskają osi kategorii, lecz tworzą luki (NaN)."""
        idx = pd.date_range("2026-10-20 00:00", periods=6, freq="1h", tz="Europe/Warsaw")
        # Pomijamy godziny 02:00 i 03:00
        df_gap = pd.DataFrame(
            {
                "fixing_1_pln_mwh": [100.0, 110.0, 140.0, 150.0],
                "fixing_2_pln_mwh": [100.0, 110.0, 140.0, 150.0],
                "cen_pln_mwh": [100.0, 110.0, 140.0, 150.0],
                "kse_contracting_status": [0.0, 0.0, 0.0, 0.0],
            },
            index=idx.delete([2, 3]),
        )
        fig = plot_price_indices_contracting_status_1h(df_gap)
        x_cats = fig.data[0].x
        assert len(x_cats) == 6, (
            "Oś musi zachować wszystkie 6 godzin pomimo braku 2 godzin w danych"
        )
        assert x_cats[2] == "02:00"
        assert x_cats[3] == "03:00"

    def test_bess_chart_aligns_mismatched_index_ranges(self):
        """Weryfikuje, że w BESS podwykresy cen i harmonogramu są spięte wspólną osią kategorii."""
        idx = pd.date_range("2026-10-20 00:00", periods=5, freq="1h", tz="Europe/Warsaw")
        # Ceny mają tylko 3 godziny, a harmonogram ma 5 godzin
        prices_df = pd.DataFrame(
            {"price_real": [200.0, 210.0, 220.0], "price_forecast": [205.0, 215.0, 225.0]},
            index=idx[:3],
        )
        sched_df = pd.DataFrame(
            {"charge_mw": [0.0] * 5, "discharge_mw": [0.0] * 5, "soc_mwh": [10.0] * 5},
            index=idx,
        )
        fig = plot_strategy_schedule(sched_df, prices_df, 100.0, "real")
        assert fig.layout.xaxis.categoryorder == "array"
        assert len(fig.layout.xaxis.categoryarray) == 5
        assert len(fig.data[0].x) == 5

    def test_multiday_chart_tickangle_and_ticks(self):
        """Weryfikuje, że dla wykresu 3-dniowego włączane jest pochylenie etykiet i rzadsze znaczniki."""
        idx = pd.date_range("2026-10-20 00:00", periods=72, freq="1h", tz="Europe/Warsaw")
        df_3d = pd.DataFrame(
            {
                "fixing_1_pln_mwh": [300.0] * 72,
                "fixing_2_pln_mwh": [300.0] * 72,
                "cen_pln_mwh": [300.0] * 72,
                "kse_contracting_status": [0.0] * 72,
            },
            index=idx,
        )
        fig = plot_price_indices_contracting_status_1h(df_3d)
        assert fig.layout.xaxis.tickangle == -45
        # Znaczniki co 6 godzin dla 3 dni (72h) -> 12 znaczników
        assert len(fig.layout.xaxis.tickvals) == 12
