import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.common.database import engine

DEFAULT_ENERGY_COLUMNS = [
    "rce_pln_mwh",
    "fixing_1_pln_mwh",
    "fixing_2_pln_mwh",
    "cen_pln_mwh",
]


@st.cache_data(ttl=900)
def get_min_max_date(index_name: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """
    Pobiera minimalną i maksymalną datę dla wskazanego indeksu cenowego z tabeli energy_prices.
    Zwraca tuple (min_date, max_date) przekonwertowane do strefy Europe/Warsaw.
    """
    query = f"""
        SELECT
            MIN(datetime_utc) AS min_date,
            MAX(datetime_utc) AS max_date
        FROM energy_prices
        WHERE {index_name} IS NOT NULL;
    """

    df = pd.read_sql(query, con=engine)

    min_date_raw = df.at[0, "min_date"]
    max_date_raw = df.at[0, "max_date"]

    if pd.isna(min_date_raw) or pd.isna(max_date_raw):
        return None, None

    min_date_local = pd.to_datetime(min_date_raw).tz_convert("Europe/Warsaw")
    max_date_local = pd.to_datetime(max_date_raw).tz_convert("Europe/Warsaw")

    return min_date_local, max_date_local


@st.cache_data(ttl=900)
def get_energy_prices(
    start_dt_utc: pd.Timestamp,
    end_dt_utc: pd.Timestamp,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Pobiera z bazy dane cenowe wyłącznie dla wybranego przedziału czasowego (UTC),
    przekształca strefę czasową do Europe/Warsaw i ustawia ją jako indeks.
    """
    selected_cols = columns if columns is not None else DEFAULT_ENERGY_COLUMNS

    query_cols = ["datetime_utc"] + [col for col in selected_cols if col != "datetime_utc"]
    cols_sql = ", ".join(query_cols)
    query = text(f"""
        SELECT
            {cols_sql}
        FROM energy_prices
        WHERE datetime_utc >= :start_dt AND datetime_utc <= :end_dt
        ORDER BY datetime_utc ASC
    """)

    df = pd.read_sql(query, con=engine, params={"start_dt": start_dt_utc, "end_dt": end_dt_utc})

    if df.empty:
        return df

    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
    if df["datetime_utc"].dt.tz is None:
        df["datetime_utc"] = df["datetime_utc"].dt.tz_localize("UTC")
    else:
        df["datetime_utc"] = df["datetime_utc"].dt.tz_convert("UTC")

    df["datetime_local"] = df["datetime_utc"].dt.tz_convert("Europe/Warsaw")
    df.set_index("datetime_local", inplace=True)
    df.drop(columns=["datetime_utc"], inplace=True)

    return df


@st.cache_data(ttl=900)
def get_kse_contracting_status(
    start_dt_utc: pd.Timestamp, end_dt_utc: pd.Timestamp
) -> pd.DataFrame:
    """
    Pobiera z bazy dane zakontraktowania wyłącznie dla wybranego przedziału czasowego (UTC),
    przekształca strefę czasową do Europe/Warsaw i ustawia ją jako indeks.
    """
    query = text("""
            SELECT
                datetime_utc,
                kse_contracting_status
            FROM energy_prices
            WHERE datetime_utc >= :start_dt AND datetime_utc <= :end_dt
            ORDER BY datetime_utc ASC
        """)

    df = pd.read_sql(query, con=engine, params={"start_dt": start_dt_utc, "end_dt": end_dt_utc})

    if df.empty:
        return df

    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
    if df["datetime_utc"].dt.tz is None:
        df["datetime_utc"] = df["datetime_utc"].dt.tz_localize("UTC")
    else:
        df["datetime_utc"] = df["datetime_utc"].dt.tz_convert("UTC")

    df["datetime_local"] = df["datetime_utc"].dt.tz_convert("Europe/Warsaw")
    df.set_index("datetime_local", inplace=True)
    df.drop(columns=["datetime_utc"], inplace=True)

    return df


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
