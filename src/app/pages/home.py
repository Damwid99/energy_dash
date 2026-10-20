import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime
import plotly.graph_objects as go

from src.app.layout import render_page_header, render_page_caution
from src.app.data_provider import get_energy_prices, get_energy_prices_and_forecasts
from src.app.components.charts import (
    plot_price_indices_contracting_status_15min,
    plot_price_indices_contracting_status_1h,
)
from src.common.timeutils import to_local_tz

render_page_header("Informacje bieżące")

text = """
Prezentowane prognozy mają charakter wyłącznie poglądowy,
zostały przygotowane na ograniczonej próbce danych i **nie stanowią** rekomendacji handlowej.
Analiza danych dostępna jest na [GitHubie](https://github.com/Damwid99/energy_forecasts).
"""
render_page_caution("UWAGA", text)

now = to_local_tz(datetime.now()).floor("D")

start_local = now - pd.Timedelta(days=1)
end_local = now + pd.Timedelta(days=2)

start_dt_utc = start_local.tz_convert("UTC")
end_dt_utc = end_local.tz_convert("UTC")

df = get_energy_prices_and_forecasts(start_dt_utc=start_dt_utc, end_dt_utc=end_dt_utc)

yesterday_df = df.loc[df.index.date == start_local.date()].copy()
today_df = df.loc[df.index.date == now.date()].copy()
tommorow_df = df.loc[df.index.date == (now + pd.Timedelta(days=1)).date()].copy()

string_today = str(now.date())
string_yesterday = str(start_local.date())
string_tommorow = str(end_dt_utc.date())


yesterday_df_1h = yesterday_df.resample("1h").agg(
    {
        "fixing_1_pln_mwh": "mean",
        "fixing_2_pln_mwh": "mean",
        "cen_pln_mwh": "mean",
        "fixing_1_forecast_pln_mwh": "mean",
        "p05": "mean",
        "p10": "mean",
        "p25": "mean",
        "p50": "mean",
        "p75": "mean",
        "p90": "mean",
        "p95": "mean",
        "kse_contracting_status": "sum",
    }
)

today_df_1h = today_df.resample("1h").agg(
    {
        "fixing_1_pln_mwh": "mean",
        "fixing_2_pln_mwh": "mean",
        "cen_pln_mwh": "mean",
        "fixing_1_forecast_pln_mwh": "mean",
        "p05": "mean",
        "p10": "mean",
        "p25": "mean",
        "p50": "mean",
        "p75": "mean",
        "p90": "mean",
        "p95": "mean",
        "kse_contracting_status": "sum",
    }
)

tommorow_df_1h = tommorow_df.resample("1h").agg(
    {
        "fixing_1_pln_mwh": "mean",
        "fixing_2_pln_mwh": "mean",
        "cen_pln_mwh": "mean",
        "fixing_1_forecast_pln_mwh": "mean",
        "p05": "mean",
        "p10": "mean",
        "p25": "mean",
        "p50": "mean",
        "p75": "mean",
        "p90": "mean",
        "p95": "mean",
        "kse_contracting_status": "sum",
    }
)


def calculate_delta(y_true, y_pred, round_: int = 2):
    delta = y_true - y_pred
    vector = np.round((delta), round_)
    mean_ = np.round(np.mean(delta), round_)
    return vector, mean_


col1, col2, col3 = st.columns(3)

with col1:
    st.subheader(string_tommorow)

    has_real = tommorow_df_1h["fixing_1_pln_mwh"].notna().all()
    has_forecast = tommorow_df_1h["fixing_1_forecast_pln_mwh"].notna().any()

    if has_real and has_forecast:
        delta_vector, delta_mean = calculate_delta(
            tommorow_df_1h["fixing_1_pln_mwh"], tommorow_df_1h["fixing_1_forecast_pln_mwh"], 2
        )
        st.metric(
            "Średnia Fixing I",
            f"{np.round(np.mean(tommorow_df_1h['fixing_1_pln_mwh']), 2)} zł",
            delta_mean,
            chart_data=delta_vector,
            chart_type="area",
            border=True,
            help="Wartość delty wyliczona na podstawie wyznaczonej prognozy Fixing I (true-real)",
        )
    elif has_forecast:
        st.metric(
            "Prognoza Fixing I",
            f"{np.round(np.mean(tommorow_df_1h['fixing_1_forecast_pln_mwh']), 2)} zł",
            0,
            chart_data=np.zeros(24),
            chart_type="area",
            border=True,
            help="Średnia dobowa prognozy Fixing I",
        )
    else:
        st.info(
            "Brak cen rzeczywistych i brak prognoz. Prognoza na jutro się jeszcze nie wykonała (brak prognoz PSE). Proszę spróbować za kilka minut..."
        )

    if tommorow_df_1h["fixing_2_pln_mwh"].notna().any():
        st.metric(
            "Średnia Fixing II",
            f"{np.mean(tommorow_df_1h['fixing_2_pln_mwh']):.2f} zł",
        )


with col2:
    st.subheader(string_today)
    delta_vector, delta_mean = calculate_delta(
        today_df_1h["fixing_1_pln_mwh"], today_df_1h["fixing_1_forecast_pln_mwh"], 2
    )
    st.metric(
        "Średnia Fixing I",
        f"{np.round(np.mean(today_df['fixing_1_pln_mwh']), 2)} zł",
        delta_mean,
        chart_data=delta_vector,
        chart_type="area",
        border=True,
        help="Wartość delty wyliczona na podstawie wyznaczonej prognozy Fixing I (true-real)",
    )
    st.metric(
        "Średnia Fixing II",
        f"{np.mean(today_df['fixing_2_pln_mwh']):.2f} zł",
    )
    st.metric(
        "Średnia CEN",
        f"{np.mean(today_df['cen_pln_mwh']):.2f} zł",
    )


with col3:
    st.subheader(string_yesterday)
    delta_vector, delta_mean = calculate_delta(
        yesterday_df_1h["fixing_1_pln_mwh"], yesterday_df_1h["fixing_1_forecast_pln_mwh"], 2
    )
    st.metric(
        "Średnia Fixing I",
        f"{np.round(np.mean(yesterday_df['fixing_1_pln_mwh']), 2)} zł",
        delta_mean,
        chart_data=delta_vector,
        chart_type="area",
        border=True,
        help="Wartość delty wyliczona na podstawie wyznaczonej prognozy Fixing I (true-real)",
    )
    st.metric(
        "Średnia Fixing II",
        f"{np.mean(yesterday_df['fixing_2_pln_mwh']):.2f} zł",
    )
    st.metric(
        "Średnia CEN",
        f"{np.mean(yesterday_df['cen_pln_mwh']):.2f} zł",
    )

granularity = st.segmented_control(
    "Interwał",
    options=["15 Minut", "1 Godzina"],
    default="15 Minut",
    label_visibility="collapsed",
)

tab_tommorrow, tab_today, tab_yesterday = st.tabs(
    [string_tommorow, string_today, string_yesterday], default=string_today
)

with tab_tommorrow:
    if granularity == "15 Minut":
        fig = plot_price_indices_contracting_status_15min(tommorow_df)
    else:
        fig = plot_price_indices_contracting_status_1h(tommorow_df_1h)

    st.plotly_chart(fig, use_container_width=True)

with tab_today:
    if granularity == "15 Minut":
        fig = plot_price_indices_contracting_status_15min(today_df)
    else:
        fig = plot_price_indices_contracting_status_1h(today_df_1h)

    st.plotly_chart(fig, use_container_width=True)


with tab_yesterday:
    if granularity == "15 Minut":
        fig = plot_price_indices_contracting_status_15min(yesterday_df)
    else:
        fig = plot_price_indices_contracting_status_1h(yesterday_df_1h)

    st.plotly_chart(fig, use_container_width=True)
