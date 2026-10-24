import pandas as pd
from sqlalchemy import text

from energy_dash.core.db import read_df
from energy_dash.core.timeutils import WARSAW

DEFAULT_ENERGY_COLUMNS = [
    "rce_pln_mwh",
    "fixing_1_pln_mwh",
    "fixing_2_pln_mwh",
    "cen_pln_mwh",
]


def get_energy_prices(
    start_dt_utc: pd.Timestamp,
    end_dt_utc: pd.Timestamp,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Pobiera dane cenowe z tabeli energy_prices i zwraca je z indeksem w czasie lokalnym."""
    selected_cols = columns if columns is not None else DEFAULT_ENERGY_COLUMNS
    query_cols = ["datetime_utc"] + [col for col in selected_cols if col != "datetime_utc"]
    cols_sql = ", ".join(query_cols)

    query = text(f"""
        SELECT {cols_sql}
        FROM energy_prices
        WHERE datetime_utc >= :start_dt AND datetime_utc <= :end_dt
        ORDER BY datetime_utc ASC
    """)
    params = {"start_dt": start_dt_utc, "end_dt": end_dt_utc}
    return read_df(query, params=params, index_col="datetime_utc", tz=WARSAW)


def get_kse_contracting_status(
    start_dt_utc: pd.Timestamp,
    end_dt_utc: pd.Timestamp,
) -> pd.DataFrame:
    """Pobiera status zakontraktowania KSE i zwraca z indeksem w czasie lokalnym"""
    query = text("""
    SELECT
        datetime_utc,
        kse_contracting_status
    FROM energy_prices
    WHERE datetime_utc >= :start_date AND datetime_utc < :end_date
    ORDER BY datetime_utc ASC
    """)
    params = {"start_date": start_dt_utc, "end_date": end_dt_utc}

    return read_df(query, params=params, index_col="datetime_utc", tz=WARSAW)


def get_min_max_date(index_name: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Pobiera minimalną i maksymalną datę dla wskazanego indeksu w czasie Europe/Warsaw."""
    query = text(f"""
    SELECT
        MIN(datetime_utc) AS min_date,
        MAX(datetime_utc) AS max_date
    FROM energy_prices
    WHERE {index_name} IS NOT NULL
    """)
    df = read_df(query, index_col=None)
    if df.empty or pd.isna(df.at[0, "min_date"]) or pd.isna(df.at[0, "max_date"]):
        return None, None

    min_date = pd.to_datetime(df.at[0, "min_date"], utc=True).tz_convert(WARSAW)
    max_date = pd.to_datetime(df.at[0, "max_date"], utc=True).tz_convert(WARSAW)

    return min_date, max_date
