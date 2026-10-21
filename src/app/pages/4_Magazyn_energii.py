import streamlit as st
import pandas as pd
from datetime import datetime
from src.app.layout import render_page_header, render_page_caution
from src.app.data_provider import get_data_for_bess
from src.ml.bess.prices import prepare_price_data
from src.ml.bess.strategies import run_day_strategies, BessStrategy
from src.ml.bess.battery import BatteryParams
from src.app.components.charts import plot_strategy_schedule
from src.ml.fix_I_forecast.predictor import load_champion_model, init_mlflow
from energy_dash.core.settings import get_settings

render_page_header("Magazyn Energii")

text = """
Prezentowane prognozy mają charakter wyłącznie poglądowy,
zostały przygotowane na ograniczonej próbce danych i **nie stanowią** rekomendacji handlowej.
Analiza danych dostępna jest na [GitHubie](https://github.com/Damwid99/energy_forecasts).
"""
render_page_caution("UWAGA", text)

now = pd.Timestamp.now(tz=get_settings().tz).floor("D")

start_local = now - pd.Timedelta(days=2)
end_local = now + pd.Timedelta(days=2)

start_dt_utc = start_local.tz_convert("UTC")
end_dt_utc = end_local.tz_convert("UTC")


string_today = str(now.date())
string_yesterday = str((now - pd.Timedelta(days=1)).date())
string_tommorow = str((now + pd.Timedelta(days=1)).date())

strategies_info = {
    BessStrategy.FORECAST_BASED: (
        "Optymalizacja prognostyczna",
        "Harmonogram wyznaczany na podstawie prognozy cen. Odzwierciedla realne działanie magazynu decydującego przed sesją rynku.",
    ),
    BessStrategy.PERFECT_FORESIGHT: (
        "Idealna wiedza",
        "Teoretyczny górny limit zysku wyznaczony na rzeczywistych cenach. Służy jako benchmark do oceny jakości prognozy.",
    ),
    BessStrategy.NAIVE: (
        "Strategia naiwna (wczorajsze ceny)",
        "Heurystyka planująca ładowanie i rozładowanie w stałych godzinach wyznaczonych na bazie cen z poprzedniej doby, bez użycia modelu optymalizującego. Nie uwzględnia wymaganego minimalnego stanu naładowania na koniec doby.",
    ),
}


@st.cache_data(ttl="6h")
def get_cached_champion_version() -> str:
    """Zwraca wersję modelu champion z MLflow, odświeżaną co 10 minut."""
    try:
        init_mlflow()
        mv = load_champion_model()
        return str(mv.version)
    except Exception as e:
        return "3"


@st.cache_data(max_entries=10, ttl="5m")
def get_cached_strategies(
    start_iso: str,
    end_iso: str,
    days_iso: list[str],
    power_mw: float,
    capacity_mwh: float,
    soc_init_pct: float,
    soc_end_min_pct: float,
    eta_roundtrip_pct: float,
    model_version: str,
):
    params = BatteryParams.from_roundtrip(
        power_mw=power_mw,
        duration_h=capacity_mwh / power_mw,
        eta_roundtrip=eta_roundtrip_pct,
        soc_init_mwh=capacity_mwh * soc_init_pct,
        soc_end_min_mwh=capacity_mwh * soc_end_min_pct,
    )

    df = get_data_for_bess(
        start_dt_utc=pd.Timestamp(start_iso),
        end_dt_utc=pd.Timestamp(end_iso),
        model_version=model_version,
    )

    df_prepared = prepare_price_data(df[["fixing_1_pln_mwh"]], df[["forecast_pln_mwh"]])

    return {
        day_str: run_day_strategies(df_prepared, pd.Timestamp(day_str).date(), params)
        for day_str in days_iso
    }


champion_version = get_cached_champion_version()
with st.sidebar:
    with st.form("battery_params_form"):
        st.subheader("Parametry magazynu")

        power_mw = st.slider(
            label="Moc przyłączeniowa [MW]",
            min_value=1.0,
            max_value=30.0,
            step=0.5,
            value=10.0,
        )

        capacity_mwh = st.slider(
            label="Pojemność użyteczna [MWh]",
            min_value=1.0,
            max_value=120.0,
            step=0.5,
            value=20.0,
        )

        soc_init_pct = st.slider(
            label="Początkowy stan naładowania [%]",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            value=0.0,
            format="percent",
        )

        with st.expander("Zaawansowane", expanded=False):
            soc_end_min_pct = st.slider(
                label="Minimalny stan naładowania na koniec doby [%]",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                value=0.0,
                format="percent",
            )

            eta_roundtrip_pct = st.slider(
                label="Sprawność cyklu [%]",
                min_value=0.7,
                max_value=0.95,
                step=0.01,
                value=0.85,
                format="percent",
            )

        submitted = st.form_submit_button("Wyznacz strategie", type="primary")


def strategy_categories_by_day(results, string_day):
    strategy_keys = results.schedules.keys()
    if not strategy_keys:
        if results.notes:
            for note in results.notes:
                st.info(note)
        return None

    strategy_names = {key: strategies_info.get(key, (key, ""))[0] for key in strategy_keys}
    selected = st.pills(
        "Strategia",
        options=strategy_keys,
        format_func=lambda x: strategies_info[x][0],
        key=f"strategy_{string_day}",
        default=next(iter(strategy_keys)),
    )

    if selected:
        st.caption("INFO", help=strategies_info[selected][1])
    return selected


days_list = [string_tommorow, string_today, string_yesterday]
strategies = get_cached_strategies(
    start_iso=start_dt_utc.isoformat(),
    end_iso=end_dt_utc.isoformat(),
    days_iso=days_list,
    power_mw=power_mw,
    capacity_mwh=capacity_mwh,
    soc_init_pct=soc_init_pct,
    soc_end_min_pct=soc_end_min_pct,
    eta_roundtrip_pct=eta_roundtrip_pct,
    model_version=champion_version,
)


tab_tommorrow, tab_today, tab_yesterday = st.tabs(
    [string_tommorow, string_today, string_yesterday], default=string_today
)

for tab, string_day in zip(
    [tab_tommorrow, tab_today, tab_yesterday],
    [string_tommorow, string_today, string_yesterday],
    strict=False,
):
    with tab:
        strat_results = strategies[string_day]
        if strat_results.notes:
            for note in strat_results.notes:
                st.info(note)
        if not strat_results.schedules:
            continue
        sum_df = strat_results.summary.copy()
        sum_df.rename(
            columns={
                "revenue_pln": "Przychód [PLN]",
                "n_cycles": "Liczba cykli",
                "capture_rate": "Wskaźnik Capture Rate",
            },
            index={key: strategies_info.get(key, [key])[0] for key in strat_results.schedules},
            inplace=True,
        )
        st.dataframe(
            sum_df.style.format(
                {
                    "Przychód [PLN]": "{:,.2f}",
                    "Liczba cykli": "{:.2f}",
                    "Wskaźnik Capture Rate": "{:.2%}",
                },
                decimal=",",
                thousands=" ",
            )
        )
        strat_select = strategy_categories_by_day(strat_results, string_day)
        if strat_select:
            strat_revenue = strat_results.summary.loc[strat_select, "revenue_pln"]
            st.plotly_chart(
                plot_strategy_schedule(
                    strat_results.schedules[strat_select],
                    strat_results.prices,
                    strat_revenue,
                    strat_results.revenue_basis,
                    strategies_info[strat_select][0],
                )
            )
