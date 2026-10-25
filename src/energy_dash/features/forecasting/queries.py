import pandas as pd
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from energy_dash.core.db import read_df

QUERY = text("""
    SELECT *
    FROM v_energy_summary
    WHERE datetime_utc >= :start_date 
      AND datetime_utc < :end_date
    ORDER BY datetime_utc ASC
""")


def get_energy_prices_and_forecasts(
    start_dt_utc: pd.Timestamp, end_dt_utc: pd.Timestamp
) -> pd.DataFrame:
    """Pobiera dane cenowe i kwantylowe prognozy dla wybranego przedziału (w czasie lokalnym)."""
    query = text("""
        WITH expanded AS (
            SELECT 
                f.datetime_utc + (n.minute || ' minutes')::interval AS datetime_utc,
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
        ORDER BY datetime_utc ASC
    """)
    params = {"start_dt": start_dt_utc, "end_dt": end_dt_utc}
    return read_df(query, params=params, index_col="datetime_utc")


def get_data_from_db(sql_query: TextClause, params: dict) -> pd.DataFrame:
    """Pobiera dane wejściowe dla modelu ML z widoku v_energy_summary.

    Zwraca DataFrame z kolumną 'datetime_utc' (bez ustawiania indeksu, gdyż
    transform_data_for_model ustawia indeks samodzielnie).
    """
    df = read_df(sql_query, params=params, index_col=None)
    if not df.empty and "datetime_utc" in df.columns:
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df
