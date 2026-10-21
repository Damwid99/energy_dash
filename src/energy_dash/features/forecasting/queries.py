import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.common.database import engine


@st.cache_data(ttl="5m")
def get_energy_prices_and_forecasts(
    start_dt_utc: pd.Timestamp, end_dt_utc: pd.Timestamp
) -> pd.DataFrame:
    """
    Pobiera z bazy dane cenowe wyłącznie dla wybranego przedziału czasowego (UTC),
    przekształca strefę czasową do Europe/Warsaw i ustawia ją jako indeks.
    """
    query = text("""
        WITH expanded AS (
            SELECT 
                f.datetime_utc + (n.minute || ' minutes')::interval AS datetime_utc,
                (f.datetime_utc + (n.minute || ' minutes')::interval) AT TIME ZONE 'Europe/Warsaw' AS datetime_local,
                f.model_version,
                f.forecast_pln_mwh AS fixing_1_forecast_pln_mwh,
                f.p05,
                f.p10,
                f.p25,
                f.p50,
                f.p75,
                f.p90,
                f.p95,
                e.fixing_1_pln_mwh,
                e.fixing_2_pln_mwh,
                e.cen_pln_mwh,
                e.rce_pln_mwh,
                e.kse_contracting_status
            FROM da_price_forecasts f
            CROSS JOIN (VALUES (0), (15), (30), (45)) AS n(minute)
            LEFT JOIN energy_prices e 
                ON e.datetime_utc = f.datetime_utc + (n.minute || ' minutes')::interval
        )
        SELECT *
        FROM expanded
        WHERE datetime_utc >= :start_dt AND datetime_utc <= :end_dt
    """)

    df = pd.read_sql(query, con=engine, params={"start_dt": start_dt_utc, "end_dt": end_dt_utc})

    if df.empty:
        return df

    df["datetime_local"] = pd.to_datetime(df["datetime_local"])
    if df["datetime_local"].dt.tz is None:
        df["datetime_local"] = df["datetime_local"].dt.tz_localize("Europe/Warsaw")
    else:
        df["datetime_local"] = df["datetime_local"].dt.tz_convert("Europe/Warsaw")

    df.set_index("datetime_local", inplace=True)
    df.drop(columns=["datetime_utc"], inplace=True)

    return df
