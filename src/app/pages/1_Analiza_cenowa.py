from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.app.data_provider import get_energy_prices, get_min_max_date
from src.app.layout import render_page_header

render_page_header("Ceny energii")
st.markdown("Monitor polskiego rynku energii. Ceny podane w `PLN/MWh`.")

price_indices = {
    "fixing_1_pln_mwh": "Fixing I",
    "fixing_2_pln_mwh": "Fixing II",
    "cen_pln_mwh": "CEN",
    "rce_pln_mwh": "RCE",
}

with st.sidebar:
    st.header("Opcje")

    selected_price = st.sidebar.selectbox(
        "Wybierz indeks cenowy:",
        options=list(price_indices.keys()),
        format_func=lambda x: price_indices[x],
    )

    min_dt_local, max_dt_local = get_min_max_date(selected_price)
    if min_dt_local is None or max_dt_local is None:
        st.warning("Brak danych dla wybranego indeksu.")
        st.stop()

    min_date = min_dt_local.date()
    max_date = max_dt_local.date()
    safe_start = max(min_date, max_date - timedelta(days=2))

    selected_dates = st.date_input(
        "Wybierz zakres dat",
        value=[safe_start, max_date],
        min_value=min_date,
        max_value=max_date,
    )

if len(selected_dates) == 1:
    start_date = selected_dates[0]
    end_date = selected_dates[0]
elif len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    st.error("Proszę wybrać początek i koniec przedziału czasowego")
    st.stop()

start_dt_local = pd.Timestamp(start_date).tz_localize("Europe/Warsaw")
end_dt_local = (
    pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
).tz_localize("Europe/Warsaw")

start_dt_utc = start_dt_local.tz_convert("UTC")
end_dt_utc = end_dt_local.tz_convert("UTC")

with st.spinner("Pobieranie danych z bazy..."):
    filtered_df = get_energy_prices(start_dt_utc, end_dt_utc)


st.subheader(f"Podsumowanie okresu: {start_date} do {end_date}")

if (
    not filtered_df.empty
    and selected_price in filtered_df.columns
    and filtered_df[selected_price].notna().any()
):
    avg_price = filtered_df[selected_price].mean()
    negative_hours = (filtered_df[selected_price] < 0).sum()
    max_price = filtered_df[selected_price].max()
    max_time_local = filtered_df[selected_price].idxmax().strftime("%Y-%m-%d %H:%M")

    col1, col2, col3 = st.columns(3)

    col1.metric("Średnia cena RCE", f"{avg_price:.2f} zł")
    col2.metric("Okresy ujemne", f"{negative_hours} h")
    col3.metric(
        "Najdroższa energia", f"{max_price:.2f} zł", delta=max_time_local, delta_color="off"
    )

else:
    st.warning("Brak danych we wskazanym przedziale")

####### Główny wykres Plotly z cenami #########

st.markdown("---")
st.subheader("Przebieg zmienności indeksu cenowego")

if not filtered_df.empty:
    fig = px.line(
        filtered_df,
        y=selected_price,
        title=price_indices[selected_price],
        labels={"datetime_local": "Data i czas (Strefa PL)", selected_price: "Cena [PLN/MWh]"},
        template="plotly_white",
    )

    # Cień pod linią i kolor
    fig.update_traces(line_color="#FF4B4B", fill="tozeroy", fillcolor="rgba(255, 75, 75, 0.1)")

    fig.update_layout(
        hovermode="x unified",
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.1)"),
        margin=dict(l=20, r=20, t=30, b=20),
    )

    st.plotly_chart(fig, use_container_width=True)

##################### Zakładki z wykresami analitycznymi ####################
tab1, tab2, tab3, tab4 = st.tabs(["Profil dobowy", "Spread cenowy", "Heatmapa", "PEAK5 | BASE"])


with tab1:
    df_hourly = filtered_df.copy()
    df_hourly["hour"] = df_hourly.index.hour

    profile = (
        df_hourly.groupby("hour")[selected_price]
        .agg(
            mean="mean",
            min="min",
            max="max",
            q25=lambda x: x.quantile(0.25),
            q75=lambda x: x.quantile(0.75),
        )
        .reset_index()
    )

    fig_profile = go.Figure()

    fig_profile.add_trace(
        go.Scatter(
            x=profile["hour"],
            y=profile["q75"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig_profile.add_trace(
        go.Scatter(
            y=profile["q25"],
            x=profile["hour"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    fig_profile.add_trace(
        go.Scatter(
            x=profile["hour"],
            y=profile["mean"],
            mode="lines+markers",
            line=dict(color="#FF4B4B", width=3),
            marker=dict(size=6),
            name="Średnia cena",
        )
    )

    fig_profile.update_layout(
        title="Średni dobowy profil cenowy",
        xaxis=dict(title="Godzina doby", tickmode="linear", dtick=2, showgrid=False),
        yaxis=dict(title="PLN/MWh", gridcolor="rgba(0,0,0,0.05)"),
        hovermode="x unified",
        template="plotly_white",
        margin=dict(l=20, r=20, t=40, b=20),
    )

    st.plotly_chart(fig_profile, use_container_width=True)
with tab2:
    MIN_COVERAGE_RATIO = 0.5

    available_compare_indices = [
        col
        for col in price_indices.keys()
        if col != selected_price
        and col in filtered_df.columns
        and filtered_df[col].notna().mean() >= MIN_COVERAGE_RATIO
    ]

    if not available_compare_indices:
        st.info("Brak innych indeksów z wystarczającym pokryciem danych (min. 50%) w tym okresie.")
    else:
        c_sel, c_mode, c_slide = st.columns([1.2, 1.2, 1.6])

        with c_sel:
            compare_price = st.selectbox(
                "Indeks odniesienia:",
                options=available_compare_indices,
                format_func=lambda x: price_indices[x],
            )

        with c_mode:
            view_mode = st.radio(
                "Rozdzielczość wykresu:",
                options=["Dni (Słupki)", "15 minut (Linie)"],
                horizontal=True,
                help="Widok dzienny agreguje dane i eliminuje szum. Widok 15-minutowy pokazuje pełną dynamikę.",
            )

        total_days = max(1, (end_date - start_date).days + 1)
        max_slider_days = max(2, min(total_days, 30))
        default_days = min(5, max_slider_days) if total_days >= 5 else 1

        with c_slide:
            rolling_days = st.slider(
                "Średnia krocząca (dni):",
                min_value=1,
                max_value=max_slider_days,
                value=default_days,
            )

        primary_name = price_indices[selected_price]
        compare_name = price_indices[compare_price]

        df_spread = filtered_df[[selected_price, compare_price]].dropna().copy()

        if df_spread.empty:
            st.warning("Brak pokrywających się danych czasowych dla obu indeksów.")
        else:
            df_spread["spread"] = df_spread[selected_price] - df_spread[compare_price]

            avg_spread = df_spread["spread"].mean()
            higher_pct = (df_spread["spread"] > 0).mean() * 100
            max_spread = df_spread["spread"].max()
            min_spread = df_spread["spread"].min()

            k1, k2, k3 = st.columns(3)
            k1.metric("Średni spread okresu", f"{avg_spread:+.2f} zł/MWh")
            k2.metric(f"Przewaga {primary_name}", f"{higher_pct:.1f}% czasu")
            k3.metric("Min / Max spread", f"{min_spread:.1f} / {max_spread:.1f} zł")

            fig_spread = go.Figure()

            # =============================================================
            # WARIANT A: AGREGACJA DZIENNA (1 SŁUPEK = 1 DZIEŃ)
            # ==========================================================
            if view_mode == "Dni (Słupki)":
                daily_spread = df_spread["spread"].resample("1D").mean().dropna().to_frame()
                daily_spread["rolling"] = (
                    daily_spread["spread"].rolling(window=rolling_days, min_periods=1).mean()
                )

                bar_colors = [
                    "#00CC96" if val >= 0 else "#EF553B" for val in daily_spread["spread"]
                ]

                fig_spread.add_trace(
                    go.Bar(
                        x=daily_spread.index,
                        y=daily_spread["spread"],
                        marker_color=bar_colors,
                        name="Średni spread dobowy",
                        hovertemplate="Dzień: %{x|%Y-%m-%d}<br>Spread śr.: %{y:.2f} PLN/MWh<extra></extra>",
                    )
                )

                fig_spread.add_trace(
                    go.Scatter(
                        x=daily_spread.index,
                        y=daily_spread["rolling"],
                        mode="lines+markers",
                        line=dict(color="#1f77b4", width=3),
                        marker=dict(size=5),
                        name=f"Trend kroczący ({rolling_days}d)",
                        hovertemplate="Śr. krocząca: %{y:.2f} PLN/MWh<extra></extra>",
                    )
                )

            # ==================================================================
            # WARIANT B: CIĄGŁY WYKRES LINIOWY DLA 15-MINUTÓWKI
            # ===================================================================
            else:
                df_spread["rolling"] = (
                    df_spread["spread"].rolling(f"{rolling_days}D", min_periods=1).mean()
                )

                fig_spread.add_trace(
                    go.Scatter(
                        x=df_spread.index,
                        y=df_spread["spread"],
                        mode="lines",
                        line=dict(color="rgba(128, 128, 128, 0.35)", width=1),
                        name="Spread surowy (15-min)",
                        hovertemplate="Czas: %{x|%Y-%m-%d %H:%M}<br>Spread: %{y:.2f} PLN<extra></extra>",
                    )
                )

                fig_spread.add_trace(
                    go.Scatter(
                        x=df_spread.index,
                        y=df_spread["rolling"],
                        mode="lines",
                        line=dict(color="#FF4B4B", width=2.5),
                        name=f"Średnia krocząca ({rolling_days}d)",
                        hovertemplate="Śr. krocząca: %{y:.2f} PLN<extra></extra>",
                    )
                )

            fig_spread.update_layout(
                title=f"Spread: <b>{primary_name}</b> minus <b>{compare_name}</b>",
                xaxis=dict(title="Czas", showgrid=False),
                yaxis=dict(
                    title="Różnica [PLN/MWh]",
                    gridcolor="rgba(0,0,0,0.05)",
                    zeroline=True,
                    zerolinecolor="rgba(0,0,0,0.5)",
                    zerolinewidth=1.5,
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified",
                template="plotly_white",
                margin=dict(l=20, r=20, t=50, b=20),
            )

            st.plotly_chart(fig_spread, use_container_width=True)

with tab3:
    df_hm = filtered_df.copy()
    df_hm["date"] = df_hm.index.strftime("%Y-%m-%d")
    df_hm["hour"] = df_hm.index.hour

    pivot_prices = df_hm.pivot_table(
        index="date", columns="hour", values=selected_price, aggfunc="mean"
    )

    custom_scale = [[0.0, "#2b83ba"], [0.5, "#ffffff"], [1.0, "#d7191c"]]

    fig_heatmap = px.imshow(
        pivot_prices,
        labels=dict(x="Godzina doby", y="Dzień", color="Cena [PLN/MWh]"),
        x=pivot_prices.columns,
        y=pivot_prices.index,
        color_continuous_scale=custom_scale,
        color_continuous_midpoint=0,
        aspect="auto",
        title=f"Heatmapa cenowa {price_indices[selected_price]} (Dzień x Godzina)",
    )

    fig_heatmap.update_layout(
        xaxis=dict(tickmode="linear", dtick=2),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

with tab4:
    st.subheader(f"Wycena Base vs Peak5 ({price_indices[selected_price]})")
    st.caption(
        "**BASE:** Średnia całodobowa (24h) | "
        "**PEAK5:** Średnia z godzin 07:00–22:00 w dni robocze (Pn–Pt)"
    )

    # 1. Przygotowanie danych i oznaczenie stref TGE
    df_tge = filtered_df.copy()
    df_tge["hour"] = df_tge.index.hour
    df_tge["dayofweek"] = df_tge.index.dayofweek  # 0-4 = Pn-Pt, 5-6 = So-Nd
    df_tge["date"] = df_tge.index.date

    is_peak = df_tge["hour"].between(7, 21) & (df_tge["dayofweek"] < 5)

    # Agregacja dzienna
    daily_base = df_tge.groupby("date")[selected_price].mean().rename("Base")
    daily_peak5 = df_tge[is_peak].groupby("date")[selected_price].mean().rename("Peak5")

    df_products = pd.concat([daily_base, daily_peak5], axis=1).reset_index()
    df_products["date_str"] = df_products["date"].astype(str)
    df_products["spread"] = df_products["Peak5"] - df_products["Base"]

    # 2. Metryki KPI dla wybranego okresu
    period_base = df_tge[selected_price].mean()
    has_workdays = is_peak.any()
    period_peak5 = df_tge.loc[is_peak, selected_price].mean() if has_workdays else None

    col_b1, col_b2, col_b3 = st.columns(3)
    col_b1.metric("BASE okresu", f"{period_base:.2f} PLN/MWh")

    if period_peak5 is not None:
        period_spread = period_peak5 - period_base
        col_b2.metric("PEAK5 okresu", f"{period_peak5:.2f} PLN/MWh")
        col_b3.metric(
            "Premia szczytowa (Peak5 - Base)",
            f"{period_spread:+.2f} PLN/MWh",
            delta=f"{period_spread:+.2f} PLN",
            delta_color="normal",  # zielony = droższy szczyt, czerwony = tańszy
        )
    else:
        col_b2.metric("PEAK5 okresu", "Brak dni roboczych")
        col_b3.metric("Premia szczytowa", "-")

    st.markdown("---")

    # 3. Wykres słupkowy: Base vs Peak5 dzień po dniu
    fig_bp = go.Figure()

    fig_bp.add_trace(
        go.Bar(
            x=df_products["date_str"],
            y=df_products["Base"],
            name="BASE (24h)",
            marker_color="#2b5c8f",
            hovertemplate="<b>%{x}</b><br>BASE: %{y:.2f} PLN/MWh<extra></extra>",
        )
    )

    fig_bp.add_trace(
        go.Bar(
            x=df_products["date_str"],
            y=df_products["Peak5"],
            name="PEAK5 (07–22 Pn-Pt)",
            marker_color="#e05638",
            hovertemplate="<b>%{x}</b><br>PEAK5: %{y:.2f} PLN/MWh<extra></extra>",
        )
    )

    # Linia odniesienia: średni Base z całego zaznaczonego zakresu
    fig_bp.add_hline(
        y=period_base,
        line_dash="dash",
        line_color="#2b5c8f",
        line_width=1.5,
        annotation_text=f"Śr. Base: {period_base:.1f} zł",
        annotation_position="top left",
    )

    fig_bp.update_layout(
        barmode="group",
        title="Dzienny BASE vs PEAK5",
        xaxis=dict(title="Dzień", type="category", showgrid=False),
        yaxis=dict(title="PLN/MWh", gridcolor="rgba(0,0,0,0.05)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20),
    )

    st.plotly_chart(
        fig_bp,
        use_container_width=True,
        config={"doubleClick": "autosize", "displayModeBar": True},
    )

    # 4. Wykres rozstępu (Spreadu): Peak5 minus Base
    if has_workdays and len(df_products.dropna(subset=["spread"])) > 1:
        st.subheader("Dzienny spread szczytowy (Peak5 − Base)")

        df_spread_plot = df_products.dropna(subset=["spread"]).copy()
        colors = ["#00CC96" if val >= 0 else "#EF553B" for val in df_spread_plot["spread"]]

        fig_spread = go.Figure()
        fig_spread.add_trace(
            go.Bar(
                x=df_spread_plot["date_str"],
                y=df_spread_plot["spread"],
                marker_color=colors,
                hovertemplate="<b>%{x}</b><br>Spread: %{y:+.2f} PLN/MWh<extra></extra>",
            )
        )

        fig_spread.add_hline(y=0, line_color="black", line_width=1)

        fig_spread.update_layout(
            title="Premia / Dyskonto godzin szczytowych",
            xaxis=dict(title="Dzień roboczy", type="category", showgrid=False),
            yaxis=dict(title="Różnica [PLN/MWh]", gridcolor="rgba(0,0,0,0.05)"),
            template="plotly_white",
            margin=dict(l=20, r=20, t=40, b=20),
        )

        st.plotly_chart(
            fig_spread,
            use_container_width=True,
            config={"doubleClick": "autosize", "displayModeBar": True},
        )

##################### Surowe dane ######################
with st.expander("Pokaż surowe dane"):
    df_display = filtered_df.copy()
    df_display.rename(columns=price_indices, inplace=True)
    df_display.index.name = "Czas"
    df_display.index = df_display.index.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(df_display)
