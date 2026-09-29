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

##################### Indeksy cenowe ####################


##################### Surowe dane ######################
with st.expander("Pokaż surowe dane"):
    df_display = filtered_df.copy()
    df_display.rename(columns=price_indices, inplace=True)
    df_display.index.name = "Czas"
    df_display.index = df_display.index.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(df_display)
