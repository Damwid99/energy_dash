import pandas as pd

LOCAL_TZ = "Europe/Warsaw"


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    idx = pd.DatetimeIndex(data.index)
    data.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    return data.sort_index()


def prepare_price_data(
    real_1h: pd.DataFrame, forecast_h: pd.DataFrame
) -> tuple[pd.DataFrame, list]:
    real_data = real_1h.copy()
    forecast = forecast_h.copy()

    real_data = _ensure_utc_index(real_data)
    forecast = _ensure_utc_index(forecast)

    real_forecasts = pd.merge(real_data, forecast, left_index=True, right_index=True, how="outer")
    real_forecasts = real_forecasts.tz_convert(tz=LOCAL_TZ)
    real_forecasts.rename(
        columns={"forecast_pln_mwh": "price_forecast", "fixing_1_pln_mwh": "price_real"},
        inplace=True,
    )
    return real_forecasts
