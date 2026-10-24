from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

WARSAW = ZoneInfo("Europe/Warsaw")


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


def to_local_tz(dt_or_df: datetime | pd.DataFrame | pd.Series, tz: ZoneInfo = WARSAW):
    """
    Konwertuje obiekt czasu lub indeks DataFrame/Series na strefę lokalną
    """
    target_tz = tz

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


def format_time_labels(dt_index: pd.Index | pd.Series | list) -> list[str]:
    """
    Generuje unikalne, chronoligczne erykiety czasu
    """
    if len(dt_index) == 0:
        return []

    idx = pd.DatetimeIndex(dt_index)
    if idx.tz is None:
        idx = idx.tz_localize(WARSAW)
    else:
        idx = idx.tz_convert(WARSAW)

    multiple_days = len(idx.normalize().unique()) > 1
    fmt = "%Y-%m-%d %H:%M" if multiple_days else "%H:%M"
    labels: list[str] = []
    seen: set[str] = set()

    for ts in idx:
        lbl = ts.strftime(fmt)
        if lbl in seen:
            labels.append(f"{lbl}a")
        else:
            seen.add(lbl)
            labels.append(lbl)
    return labels


def reindex_to_regular_grid(
    df: pd.DataFrame,
    freq: str = "1h",
) -> pd.DataFrame:
    """
    Dopenia ewentualne luki w danych siatką regularn (NaN)
    """

    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df

    idx = df.index
    tz = idx.tz or WARSAW
    idx_utc = idx.tz_convert("UTC") if idx.tz else idx.tz_localize("UTC")
    full_grid_utc = pd.date_range(start=idx_utc.min(), end=idx_utc.max(), freq=freq)
    return df.reindex(full_grid_utc.tz_convert(tz))
