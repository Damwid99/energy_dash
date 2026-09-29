import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime
import plotly.graph_objects as go
import plotly.express as px
from src.app.layout import render_page_header
from src.app.data_provider import (
    get_assets_metadata,
    get_assets_capacity_factors,
    get_asset_geneartion_and_prices,
)

render_page_header("Analiza asetów wytwórczych")

asets_metadata = get_assets_metadata()
asets_capacity_factors = get_assets_capacity_factors()

st.subheader("Mapa asetów")

col_map, col_details = st.columns([2.5, 1], gap="large")
with col_map:
    fig = px.scatter_map(
        asets_metadata,
        lat="latitude",
        lon="longitude",
        hover_name="name",
        hover_data={
            "latitude": False,
            "longitude": False,
            "technology": True,
            "capacity_mw": True,
            "region": True,
        },
        color="technology",
        zoom=5,
        center={"lat": 52.0, "lon": 19.0},
        map_style="carto-darkmatter",
        custom_data=["code"],
    )

    fig.update_traces(marker=dict(size=15))
    fig.update_layout(height=600, margin={"r": 0, "t": 0, "l": 0, "b": 0})
    event = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun", selection_mode="points"
    )

    if len(event.selection["points"]) > 0:
        clicked_code = event.selection["points"][0]["customdata"][0]
        if (
            "selected_farm" not in st.session_state
            or st.session_state["selected_farm"]["code"] != clicked_code
        ):
            selected_row = asets_metadata[asets_metadata["code"] == clicked_code]
            st.session_state["selected_farm"] = selected_row.iloc[0].to_dict()
            st.session_state["show_details"] = False

with col_details:
    if "selected_farm" in st.session_state:
        farm = st.session_state["selected_farm"]
        with st.container(border=True):
            capacity_factor = asets_capacity_factors.loc[
                asets_capacity_factors["farm_id"] == farm["id"]
            ]["capacity_factor"].values[0]
            st.subheader(f"{'☀️' if farm['technology'] == 'solar' else '💨'} {farm['name']}")
            st.caption(f"{farm['technology']}")
            st.caption(f"Kod jednostki: {farm.get('code', 'N/A')}")

            st.metric("Moc zainstalowana", f"{farm['capacity_mw']} MW")
            st.metric("Region", farm["region"])

            st.markdown("---")
            st.markdown("**Bieżące warunki (Symulacja)**")
            st.progress(
                capacity_factor,
                text=f"Współczynnik wykorzystania mocy (Capacity Factor): {capacity_factor * 100:.2f}%",
            )

            if st.button(
                "Szczegółowa analityka produkcji", type="primary", use_container_width=True
            ):
                st.session_state["show_details"] = True
    else:
        st.info("Kliknij punkt na mapie, aby załadować parametry operacyjne jednostki wytwórczej.")

if st.session_state.get("show_details"):
    farm_data = get_asset_geneartion_and_prices(asset_id=farm["id"]).copy()

    farm_data["month"] = farm_data.index.to_period("M")
    farm_data["forecast_error"] = farm_data["generation_forecast_mwh"] - farm_data["generation_mwh"]
    farm_data["abs_error"] = farm_data["forecast_error"].abs()

    available_months = sorted(farm_data["month"].unique())

    if "selected_month" not in st.session_state or st.session_state["selected_month"] is None:
        st.session_state["selected_month"] = available_months[-1]

    with st.sidebar:
        st.markdown("### Parametry analizy")

        selected_month = st.selectbox(
            "Wybierz miesiąc do analizy:",
            available_months,
            key="selected_month",
        )
else:
    st.session_state["selected_month"] = None


if st.session_state.get("show_details"):
    month_data = farm_data[farm_data["month"] == selected_month]
    start_date, end_date = (month_data.index.min().date(), month_data.index.max().date())
    st.markdown(f"## Analiza farmy {farm['name']}")
    st.markdown(f" *Analiza obejmuje zakres od {str(start_date)} - {str(end_date)}*")

    tab1, tab2, tab3 = st.tabs(["Jakość prognoz", "Capacity Factor", "Profil"])
    with tab1:
        st.markdown("### Jakość prognoz")
        safe_actual = month_data["generation_mwh"].replace(0, float("nan"))

        mape = (month_data["abs_error"] / safe_actual).mean()
        mae = month_data["abs_error"].mean()
        rmse = (month_data["forecast_error"] ** 2).mean() ** 0.5
        bias = month_data["forecast_error"].mean()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("MAPE", f"{mape:.2%}")

        with col2:
            st.metric("MAE", f"{mae:.3f} MWh")

        with col3:
            st.metric("RMSE", f"{rmse:.3f} MWh")

        with col4:
            st.metric("Bias", f"{bias:.3f} MWh")

        st.markdown("### Wykres błędu prognozy (Bias w czasie)")

        fig = px.line(
            month_data,
            x=month_data.index,
            y="forecast_error",
            title=f"Błąd prognozy (forecast - actual) — {selected_month}",
            labels={"forecast_error": "Błąd prognozy [MWh]", "index": "Data"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown("### Capacity Factor (CF)")

        monthly_cf = month_data["generation_mwh"].sum() / (farm["capacity_mw"] * len(month_data))

        col1, col2 = st.columns(2)
        with col1:
            st.metric("CF miesięczny", f"{monthly_cf:.2f}")

        daily_cf = (
            month_data["generation_mwh"].groupby(month_data.index.date).sum() / farm["capacity_mw"]
        )

        with col2:
            st.metric("Średni CF dzienny", f"{daily_cf.mean():.2f}")

        st.markdown("### CF dzienny (wykres)")

        fig_daily = px.line(
            x=daily_cf.index,
            y=daily_cf.values,
            labels={"x": "Dzień", "y": "CF dzienny"},
            title="Capacity Factor — dzienny profil",
        )
        st.plotly_chart(fig_daily, use_container_width=True)

        st.markdown("### CF godzinowy (wykres)")

        hourly_cf = month_data["generation_mwh"] / farm["capacity_mw"]

        fig_hourly = px.line(
            x=month_data.index,
            y=hourly_cf,
            labels={"x": "Data", "y": "CF godzinowy"},
            title="Capacity Factor — godzinowy profil",
        )
        st.plotly_chart(fig_hourly, use_container_width=True)

    with tab3:
        st.markdown("### Profil assetu")

        revenue_actual = (month_data["generation_mwh"] * month_data["cen_pln_mwh"]).sum()

        revenue_forecast = (month_data["generation_forecast_mwh"] * month_data["cen_pln_mwh"]).sum()

        if month_data["generation_mwh"].sum() > 0:
            capture_price = (
                month_data["generation_mwh"] * month_data["cen_pln_mwh"]
            ).sum() / month_data["generation_mwh"].sum()
        else:
            capture_price = float("nan")

        balancing_cost_total = (
            month_data["forecast_error"].abs() * month_data["cen_pln_mwh"]
        ).sum()

        if month_data["generation_mwh"].sum() > 0:
            balancing_cost_intensity = balancing_cost_total / month_data["generation_mwh"].sum()
        else:
            balancing_cost_intensity = float("nan")

        spread_fixing = (month_data["fixing_2_pln_mwh"] - month_data["fixing_1_pln_mwh"]).mean()

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Przychód rzeczywisty", f"{revenue_actual:,.0f} PLN")

        with col2:
            st.metric("Przychód forecastowany", f"{revenue_forecast:,.0f} PLN")

        with col3:
            st.metric("Koszt bilansowania (PLN/MWh)", f"{balancing_cost_intensity:,.2f}")

        col4, col5 = st.columns(2)

        with col4:
            st.metric("Capture Price", f"{capture_price:,.2f} PLN/MWh")

        with col5:
            st.metric("Spread (Fix2 - Fix1)", f"{spread_fixing:,.2f} PLN/MWh")

        st.markdown("#### Różnica wolumenu prognozowanego i rzeczywistego vs cena bilansująca")

        fig_diff = go.Figure()

        fig_diff.add_trace(
            go.Bar(
                x=month_data.index,
                y=month_data["forecast_error"],
                name="Błąd prognozy (forecast - actual)",
                marker_color="#3498db",
                opacity=0.7,
            )
        )

        fig_diff.add_trace(
            go.Scatter(
                x=month_data.index,
                y=month_data["cen_pln_mwh"],
                name="Cena bilansująca (cen_pln_mwh)",
                mode="lines",
                line=dict(color="#e67e22", width=3),
                yaxis="y2",
            )
        )

        fig_diff.update_layout(
            title="Błąd prognozy vs cena bilansująca",
            xaxis=dict(title="Data"),
            yaxis=dict(title="Błąd prognozy [MWh]"),
            yaxis2=dict(title="Cena bilansująca [PLN/MWh]", overlaying="y", side="right"),
            legend=dict(orientation="h"),
            bargap=0.2,
            height=450,
        )

        st.plotly_chart(fig_diff, use_container_width=True)
