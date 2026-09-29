from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.app.data_provider import get_energy_prices
from src.app.layout import render_page_header

render_page_header("Dynamiczne ceny energii (RCE)")
st.markdown("Monitor rynku bilansującego. Ceny podane w `PLN/MWh`.")

with st.spinner("Pobieranie danych z bazy..."):
    df = get_energy_prices()

if df.empty:
    st.warning("Brak danych w bazie")
    st.stop()


min_date = df.index.min().date()
max_date = df.index.max().date()
safe_start = max(min_date, max_date - timedelta(days=2))

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
    selected_dates = st.sidebar.date_input(
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

start_dt = pd.Timestamp(start_date)

end_dt = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

if df.index.tz is not None:
    start_dt = start_dt.tz_localize(df.index.tz)
    end_dt = end_dt.tz_localize(df.index.tz)

filtered_df = df.loc[(df.index >= start_dt) & (df.index <= end_dt)].copy()

st.subheader(f"Podsumowanie okresu: {start_date} do {end_date}")

if not filtered_df.empty:
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
    )

    st.plotly_chart(fig, use_container_width=True)

with st.expander("Pokaż surowe dane"):
    df_display = filtered_df.copy()
    df_display.rename(columns=price_indices, inplace=True)
    df_display.index.name = "Czas"
    df_display.index = df_display.index.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(df_display)
