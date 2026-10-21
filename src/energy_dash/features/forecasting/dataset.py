import pandas as pd

from energy_dash.core.settings import get_settings
from energy_dash.core.timeutils import to_local_tz
from energy_dash.features.forecasting.features import ALL_COLUMNS, TARGET, make_training_frame


def get_start_end_date(window_size: int = 365, today: pd.Timestamp | None = None):
    if today is None:
        today = pd.Timestamp.now(tz=get_settings().tz)
    today = to_local_tz(today).normalize()

    start_train_date = (today - pd.DateOffset(days=window_size)).tz_convert("UTC")
    start_predict_date = (today + pd.DateOffset(days=1)).tz_convert("UTC")
    end_predict_date = (today + pd.DateOffset(days=2)).tz_convert("UTC")
    end_train_date = start_predict_date

    return start_train_date, end_train_date, start_predict_date, end_predict_date


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
