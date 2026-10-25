import pandas as pd
from sqlalchemy import text

from energy_dash.core.db import read_df


def get_assets_metadata() -> pd.DataFrame:
    """Zwraca metadane farm wiatrowych i słonecznych."""
    query = text("SELECT * FROM renewable_farms ORDER BY id ASC")
    return read_df(query, index_col=None)


def get_assets_capacity_factors() -> pd.DataFrame:
    """Zwraca capacity factor poszczególnych farm."""
    query = text("""
        SELECT
            f.id AS farm_id,
            f.name,
            f.capacity_mw,
            SUM(g.generation_mwh) AS total_mwh,
            COUNT(g.datetime_utc) AS hours_count,
            SUM(g.generation_mwh) / (f.capacity_mw * COUNT(g.datetime_utc)) AS capacity_factor
        FROM renewable_farms f
        LEFT JOIN renewable_generation g ON g.farm_id = f.id
        GROUP BY f.id, f.name, f.capacity_mw
    """)
    return read_df(query, index_col=None)


def get_asset_geneartion_and_prices(asset_id: int, dropna: bool = True) -> pd.DataFrame:
    """Pobiera profil generacji farmy połączony z cenami energii w czasie lokalnym."""
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
        LEFT JOIN hourly_prices hp ON hp.hour = g.datetime_utc
        WHERE g.farm_id = :farm_id
        ORDER BY g.datetime_utc ASC
    """)
    df = read_df(query, params={"farm_id": asset_id}, index_col="datetime_utc")
    if dropna and not df.empty:
        df = df.dropna()
    return df
