import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime
import plotly.graph_objects as go

from src.app.layout import render_page_header
from src.app.data_provider import get_energy_prices
from src.app.components.charts import plot_price_indices_contracting_status

render_page_header("Informacje bieżące")

now = pd.Timestamp.now(tz="Europe/Warsaw").floor("D")
start_local = now - pd.Timedelta(days=1)
end_local = now + pd.Timedelta(days=1)
start_dt_utc = start_local.tz_convert("UTC")
end_dt_utc = end_local.tz_convert("UTC")

df = get_energy_prices(
    start_dt_utc=start_dt_utc,
    end_dt_utc=end_dt_utc,
    columns=["fixing_1_pln_mwh", "fixing_2_pln_mwh", "cen_pln_mwh", "kse_contracting_status"],
)

yesterday_df = df.loc[str(start_local.date())].copy()
today_df = df.loc[str(now.date())].copy()
string_today = str(now.date())
string_yesterday = str(start_local.date())

today_df_1h = today_df.resample("1h").agg(
    {
        "fixing_1_pln_mwh": "mean",
        "fixing_2_pln_mwh": "mean",
        "cen_pln_mwh": "mean",
        "kse_contracting_status": "sum",
    }
)

yesterday_df_df_1h = yesterday_df.resample("1h").agg(
    {
        "fixing_1_pln_mwh": "mean",
        "fixing_2_pln_mwh": "mean",
        "cen_pln_mwh": "mean",
        "kse_contracting_status": "sum",
    }
)


def get_background_colors(
    status_series, pos_color="rgba(59, 130, 246, 0.25)", neg_color="rgba(239, 68, 68, 0.25)"
):
    conditions = [status_series > 0, status_series < 0]
    choices = [pos_color, neg_color]
    return np.select(conditions, choices, default="rgba(0,0,0,0)")


col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        f"Średnia Fixing I ({string_yesterday})",
        f"{yesterday_df.mean()['fixing_1_pln_mwh']:.2f} zł",
    )
    st.metric(
        f"Średnia Fixing I ({string_today})",
        f"{today_df.mean()['fixing_1_pln_mwh']:.2f} zł",
    )

with col2:
    st.metric(
        f"Średnia Fixing II ({string_yesterday})",
        f"{yesterday_df.mean()['fixing_2_pln_mwh']:.2f} zł",
    )
    st.metric(
        f"Średnia Fixing II ({string_today})",
        f"{today_df.mean()['fixing_2_pln_mwh']:.2f} zł",
    )


with col3:
    st.metric(
        f"Średnia Fixing CEN ({string_yesterday})",
        f"{yesterday_df.mean()['cen_pln_mwh']:.2f} zł",
    )
    st.metric(
        f"Średnia Fixing CEN ({string_today})",
        f"{today_df.mean()['cen_pln_mwh']:.2f} zł",
    )


tab1, tab2 = st.tabs([f"{string_today}", f"{string_yesterday}"])

with tab1:
    st.plotly_chart(
        plot_price_indices_contracting_status(today_df, today_df_1h), use_container_width=True
    )


with tab2:
    st.plotly_chart(
        plot_price_indices_contracting_status(yesterday_df, yesterday_df_df_1h),
        use_container_width=True,
    )
