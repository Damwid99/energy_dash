import pandas as pd

from src.common.timeutils import ensure_utc_index, to_local_tz

# def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
#     data = df.copy()
#     idx = pd.DatetimeIndex(data.index)
#     data.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
#     return data.sort_index()


def prepare_price_data(
    real_1h: pd.DataFrame, forecast_h: pd.DataFrame
) -> tuple[pd.DataFrame, list]:
    real_data = real_1h.copy()
    forecast = forecast_h.copy()

    real_data = ensure_utc_index(real_data)
    forecast = ensure_utc_index(forecast)

    real_forecasts = pd.merge(real_data, forecast, left_index=True, right_index=True, how="outer")
    real_forecasts = to_local_tz(real_forecasts)
    real_forecasts.rename(
        columns={"forecast_pln_mwh": "price_forecast", "fixing_1_pln_mwh": "price_real"},
        inplace=True,
    )
    return real_forecasts
