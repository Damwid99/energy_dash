import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime
import plotly.graph_objects as go
import plotly.express as px
from src.app.layout import render_page_header
from src.app.data_provider import get_assets_metadata

render_page_header("Analiza asetów wytwórczych")

asets_metadata = get_assets_metadata()

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
        selected_row = asets_metadata[asets_metadata["code"] == clicked_code]

        selected_farm_data = selected_row.iloc[0].to_dict()
        st.session_state["selected_farm"] = selected_farm_data

with col_details:
    st.markdown("### Szablon Farmy")
    if "selected_farm" in st.session_state:
        farm = st.session_state["selected_farm"]
        with st.container(border=True):
            st.subheader(f"{'☀️' if farm['technology'] == 'solar' else '💨'} {farm['name']}")
            st.caption(f"{farm['technology']}")
            st.caption(f"Kod jednostki: {farm.get('code', 'N/A')}")

            st.metric("Moc zainstalowana", f"{farm['capacity_mw']} MW")
            st.metric("Region", farm["region"])

            st.markdown("---")
            st.markdown("**Bieżące warunki (Symulacja)**")
            st.progress(0.75, text="Współczynnik wykorzystania mocy (Capacity Factor): 75%")

            if st.button(
                "Szczegółowa analityka produkcji", type="primary", use_container_width=True
            ):
                st.toast("W przyszłości przekieruje do szczegółów jednostki!")
    else:
        st.info("Kliknij punkt na mapie, aby załadować parametry operacyjne jednostki wytwórczej.")

st.write(asets_metadata)
