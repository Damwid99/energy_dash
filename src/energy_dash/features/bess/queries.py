import pandas as pd
from sqlalchemy import text

from energy_dash.core.db import read_df


def get_data_for_bess(
    start_dt_utc: str,
    end_dt_utc: str,
    model_version: str = "3",
) -> pd.DataFrame:
    """Pobiera dane cenowe i prognozy w ujęciu godzinowym z indeksem w UTC dla optymalizatora BESS."""
    query = text("""
        WITH energy_prices_hourly AS (
            SELECT
                date_trunc('hour', datetime_utc) AS datetime_utc,
                AVG(fixing_1_pln_mwh) AS fixing_1_pln_mwh
            FROM energy_prices
            GROUP BY 1
        )
        SELECT
            f.datetime_utc,
            f.forecast_pln_mwh,
            e.fixing_1_pln_mwh
        FROM da_price_forecasts f
        LEFT JOIN energy_prices_hourly e ON e.datetime_utc = f.datetime_utc
        WHERE f.datetime_utc >= :start_dt
          AND f.datetime_utc <= :end_dt
          AND f.model_version = :model_version
        ORDER BY f.datetime_utc ASC
    """)
    params = {"start_dt": start_dt_utc, "end_dt": end_dt_utc, "model_version": model_version}
    return read_df(query, params=params, index_col="datetime_utc", tz=None)
