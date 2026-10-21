from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause
from src.common.config import get_settings

from energy_dash.core.db import engine
from energy_dash.core.timeutils import to_local_tz
from src.ml.fix_I_forecast.features import ALL_COLUMNS, TARGET, make_training_frame

QUERY = text("""
    SELECT *
    FROM v_energy_summary
    WHERE datetime_utc >= :start_date 
      AND datetime_utc < :end_date
    ORDER BY datetime_utc ASC
""")
WARSAW_TZ = ZoneInfo("Europe/Warsaw")


def get_start_end_date(window_size: int = 365, today: pd.Timestamp | None = None):
    if today is None:
        today = pd.Timestamp.now(tz=get_settings().tz)
    today = to_local_tz(today).normalize()

    start_train_date = (today - pd.DateOffset(days=window_size)).tz_convert("UTC")
    start_predict_date = (today + pd.DateOffset(days=1)).tz_convert("UTC")
    end_predict_date = (today + pd.DateOffset(days=2)).tz_convert("UTC")
    end_train_date = start_predict_date

    return start_train_date, end_train_date, start_predict_date, end_predict_date


def get_data_from_db(sql_query: TextClause, params: dict) -> pd.DataFrame:
    try:
        with engine.connect() as connection:
            return pd.read_sql_query(
                sql=sql_query,
                con=connection,
                params=params,
                parse_dates=["datetime_utc"],
            )
    except Exception as e:
        raise RuntimeError(f"Błąd pobierania danych z bazy: {e}") from e


def create_train_target_set(
    data: pd.DataFrame,
    start_train_date: pd.Timestamp,
    end_train_date: pd.Timestamp,
    start_predict_date: pd.Timestamp,
    end_predict_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    train_mask = (data.index >= start_train_date) & (data.index < end_train_date)
    target_mask = (data.index >= start_predict_date) & (data.index < end_predict_date)

    train_set = data[train_mask].copy()
    target_set = data[target_mask].copy()

    return target_set, train_set


def transform_data_for_model(
    data: pd.DataFrame,
    start_train_date: pd.Timestamp,
    end_train_date: pd.Timestamp,
    start_predict_date: pd.Timestamp,
    end_predict_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    df = data.copy()
    df.set_index("datetime_utc", inplace=True)

    df = make_training_frame(df, dropna=False)
    target_set, train_set = create_train_target_set(
        df, start_train_date, end_train_date, start_predict_date, end_predict_date
    )
    train_set = train_set.dropna(subset=[*ALL_COLUMNS, TARGET])
    target_set = target_set.dropna(subset=ALL_COLUMNS)
    y_train = train_set[TARGET]

    return target_set, train_set, y_train


if __name__ == "__main__":
    start_train_date, end_train_date, start_predict_date, end_predict_date = get_start_end_date(60)
    df = get_data_from_db(
        sql_query=QUERY, params={"start_date": start_train_date, "end_date": end_predict_date}
    )
    target_set, train_set, y_train = transform_data_for_model(
        df, start_train_date, end_train_date, start_predict_date, end_predict_date
    )
