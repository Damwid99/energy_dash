import pandas as pd
import streamlit as st
from sqlalchemy import text

from energy_dash.core.db import engine
from energy_dash.core.settings import get_settings

LOCAL_TZ = get_settings().tz


@st.cache_data(ttl=900)
def get_assets_metadata() -> pd.DataFrame:
    """
    Zwraca dataframe ze wszystkimi metdanymi farm wiatrowych i słonecznych
    """

    query = text("""
        SELECT * FROM renewable_farms
        """)

    df = pd.read_sql(query, con=engine)

    return df


@st.cache_data(ttl=900)
def get_assets_capacity_factors() -> pd.DataFrame:
    """
    Zwraca dataframe z capcity factors farm
    """

    query = text("""
        SELECT
            f.id AS farm_id,
            f.name,
            f.capacity_mw,
            SUM(g.generation_mwh) AS total_mwh,
            COUNT(g.datetime_utc) AS hours_count,
            SUM(g.generation_mwh) / (f.capacity_mw * COUNT(g.datetime_utc)) AS capacity_factor
        FROM renewable_farms f
        LEFT JOIN renewable_generation g
            ON g.farm_id = f.id
        GROUP BY f.id, f.name, f.capacity_mw
        """)

    df = pd.read_sql(query, con=engine)

    return df


@st.cache_data(ttl=900)
def get_asset_geneartion_and_prices(asset_id: int, dropna: bool = True) -> pd.DataFrame:
    """
    Zwraca dataframe z generacją farm, prognozami generacji oraz indeksami cenowymi
    """

    query = text("""
        WITH hourly_prices AS (
            SELECT
                date_trunc('hour', datetime_utc) AS hour,
                AVG(fixing_1_pln_mwh) AS fixing_1_pln_mwh,
                AVG(fixing_2_pln_mwh) AS fixing_2_pln_mwh,
                AVG(cen_pln_mwh) AS cen_pln_mwh
            FROM energy_prices
            GROUP BY date_trunc('hour', datetime_utc)
        )

        SELECT
            g.farm_id,
            g.datetime_utc,
            g.generation_mwh,
            g.generation_forecast_mwh,
            hp.fixing_1_pln_mwh,
            hp.fixing_2_pln_mwh,
            hp.cen_pln_mwh
        FROM renewable_generation g
        LEFT JOIN hourly_prices hp
            ON hp.hour = g.datetime_utc
        WHERE g.farm_id = :farm_id
        ORDER BY g.datetime_utc;
        """)
    df = pd.read_sql(query, con=engine, params={"farm_id": asset_id})

    if df.empty:
        return df

    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
    if df["datetime_utc"].dt.tz is None:
        df["datetime_utc"] = df["datetime_utc"].dt.tz_localize("UTC")
    else:
        df["datetime_utc"] = df["datetime_utc"].dt.tz_convert("UTC")

    df["datetime_local"] = df["datetime_utc"].dt.tz_convert(LOCAL_TZ)
    df.set_index("datetime_local", inplace=True)
    df.drop(columns=["datetime_utc"], inplace=True)

    if dropna:
        df = df.dropna()
    return df
