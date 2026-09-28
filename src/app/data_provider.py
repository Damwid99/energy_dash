import pandas as pd
import streamlit as st

from src.common.database import engine


@st.cache_data(ttl=900)
def get_energy_prices() -> pd.DataFrame:
    """
    Pobiera dane cen z bazy danych do DataFrame w Pandas, przekształca strefę czasową do lokalnej
    i ustawia ją jako indeks
    """
    query = """
        SELECT
            datetime_utc,
            rce_pln_mwh,
            fixing_1_pln_mwh,
            fixing_2_pln_mwh
        FROM energy_prices
        ORDER BY datetime_utc ASC
    """

    df = pd.read_sql(query, con=engine)

    if df.empty:
        return df

    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"]).dt.tz_convert("UTC")

    df["datetime_local"] = df["datetime_utc"].dt.tz_convert("Europe/Warsaw")

    df.set_index("datetime_local", inplace=True)
    df.drop(columns=["datetime_utc"], inplace=True)

    return df
