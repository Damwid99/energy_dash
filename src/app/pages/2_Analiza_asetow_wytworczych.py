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
    map_style="carto-positron",
)

fig.update_traces(marker=dict(size=15))
fig.update_layout(height=600, margin={"r": 0, "t": 0, "l": 0, "b": 0})
event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points")

if len(event.selection["points"]) > 0:
    clicked_point_index = event.selection["points"][0]["point_index"]
    selected_farm_data = asets_metadata.iloc[clicked_point_index].to_dict()

    st.session_state["selected_farm"] = selected_farm_data

if "selected_farm" in st.session_state:
    st.write(st.session_state["selected_farm"])
