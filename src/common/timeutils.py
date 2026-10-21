from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.config.settings import get_settings


def ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Zapewnia indeks DatetimeIndex w strefie UTC. Sortuje.
    """
    if df.empty:
        return df.copy()
    data = df.copy()

    if not isinstance(data.index, pd.DatetimeIndex):
        try:
            data.index = pd.to_datetime(data.index)
        except Exception as err:
            raise ValueError(
                f"Nie można przekonwertować indeksu typu '{type(df.index).__name__}' "
                f"na DatetimeIndex. Wartości w indeksie muszą reprezentować daty/godziny."
            ) from err

    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    else:
        data.index = data.index.tz_convert("UTC")

    return data.sort_index()


def to_local_tz(dt_or_df: datetime | pd.DataFrame | pd.Series, tz: ZoneInfo | None = None):
    """
    Konwertuje obiekt czasu lub indeks DataFrame/Series na strefę lokalną
    """
    target_tz = tz or get_settings().tz

    if isinstance(dt_or_df, (datetime, pd.Timestamp)):
        ts = pd.Timestamp(dt_or_df)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(target_tz)

    if isinstance(dt_or_df, (pd.DataFrame, pd.Series)):
        data = dt_or_df.copy()
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        if data.index.tz is None:
            data.index = data.index.tz_localize("UTC")
        data.index = data.index.tz_convert(target_tz)
        return data

    raise TypeError(f"Nieobsługiwany typ: {type(dt_or_df)}")
