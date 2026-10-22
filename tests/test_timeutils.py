from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from energy_dash.core.timeutils import ensure_utc_index, to_local_tz


def test_ensure_utc_index_empty_df():
    """Pusty DataFrame powinien zostać zwrócony bez błędów jako kopia."""
    empty_df = pd.DataFrame(columns=["a", "b"])
    res = ensure_utc_index(empty_df)
    assert res.empty
    assert res is not empty_df


def test_ensure_utc_index_from_naive_datetime_index():
    """Naiwny DatetimeIndex powinien zostać zlokalizowany jako UTC i posortowany."""
    idx = pd.to_datetime(["2026-10-20 02:00:00", "2026-10-20 00:00:00", "2026-10-20 01:00:00"])
    df = pd.DataFrame({"val": [2, 0, 1]}, index=idx)

    res = ensure_utc_index(df)

    assert isinstance(res.index, pd.DatetimeIndex)
    assert str(res.index.tz) == "UTC"
    assert list(res["val"]) == [0, 1, 2]
    assert res.index.is_monotonic_increasing


def test_ensure_utc_index_from_warsaw_tz():
    """Indeks w strefie Europe/Warsaw (CEST +02:00) powinien zostać poprawnie przeliczony na UTC."""
    idx = pd.date_range("2026-08-01 00:00", periods=3, freq="h", tz="Europe/Warsaw")
    df = pd.DataFrame({"val": [10, 20, 30]}, index=idx)

    res = ensure_utc_index(df)

    assert str(res.index.tz) == "UTC"
    assert res.index[0] == pd.Timestamp("2026-07-31 22:00:00", tz="UTC")


def test_ensure_utc_index_from_string_index():
    """Indeks zawierający poprawne stringi dat powinien zostać skonwertowany na DatetimeIndex UTC."""
    df = pd.DataFrame({"val": [1, 2]}, index=["2026-10-20 10:00", "2026-10-20 11:00"])
    res = ensure_utc_index(df)
    assert isinstance(res.index, pd.DatetimeIndex)
    assert str(res.index.tz) == "UTC"


def test_ensure_utc_index_invalid_index_raises_value_error():
    """Niedatowy indeks (np. losowe napisy) musi rzucić czytelny ValueError."""
    df = pd.DataFrame({"val": [1, 2]}, index=["nie-data-1", "nie-data-2"])
    with pytest.raises(ValueError, match="Nie można przekonwertować indeksu"):
        ensure_utc_index(df)


def test_to_local_tz_datetime_and_timestamp():
    """Konwersja pojedynczego obiektu datetime oraz pd.Timestamp z UTC do czasu polskiego."""
    dt_utc_summer = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
    dt_local_summer = to_local_tz(dt_utc_summer)
    assert dt_local_summer.hour == 12  # CEST = UTC+2
    assert dt_local_summer.tzinfo == ZoneInfo("Europe/Warsaw")

    dt_utc_winter = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    dt_local_winter = to_local_tz(dt_utc_winter)
    assert dt_local_winter.hour == 11  # CET = UTC+1

    ts_utc = pd.Timestamp("2026-10-20 12:00:00", tz="UTC")
    ts_local = to_local_tz(ts_utc)
    assert ts_local.hour == 14


def test_to_local_tz_dataframe_and_series():
    """Konwersja DataFrame i Series z indeksem UTC oraz naiwnym na Europe/Warsaw."""
    idx_utc = pd.date_range("2026-01-10 00:00", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame({"price": [100.0, 200.0, 300.0, 400.0]}, index=idx_utc)

    df_local = to_local_tz(df)
    assert str(df_local.index.tz) == "Europe/Warsaw"
    assert df_local.index[0].hour == 1  # Zima: 00:00 UTC -> 01:00 CET

    # Naiwny Series
    s_naive = pd.Series([10, 20], index=pd.date_range("2026-07-01 00:00", periods=2, freq="h"))
    s_local = to_local_tz(s_naive)
    assert str(s_local.index.tz) == "Europe/Warsaw"
    assert s_local.index[0].hour == 2  # Lato: 00:00 UTC -> 02:00 CEST


def test_to_local_tz_dst_transition_autumn_25h():
    """Weryfikuje zachowanie przy zmianie czasu z letniego na zimowy (25 godzin w dobie 2026-10-25)."""
    idx_utc = pd.date_range("2026-10-24 22:00", "2026-10-25 22:00", freq="h", tz="UTC")
    df = pd.DataFrame({"val": range(len(idx_utc))}, index=idx_utc)

    df_local = to_local_tz(df)
    dates = df_local.index.date
    assert (dates == datetime(2026, 10, 25).date()).sum() == 25


def test_to_local_tz_naive_timestamp():
    """Naiwny pd.Timestamp przekazywany do to_local_tz powinien być traktowany jako UTC (tak jak DataFrame)."""
    ts_naive = pd.Timestamp("2026-07-15 10:00:00")
    ts_local = to_local_tz(ts_naive)
    assert ts_local.hour == 12
    assert str(ts_local.tzinfo) == "Europe/Warsaw"


def test_to_local_tz_unsupported_type_raises():
    """Przekazanie nieobsługiwanego typu (np. liczby lub listy) musi rzucić TypeError."""
    with pytest.raises(TypeError, match="Nieobsługiwany typ"):
        to_local_tz([1, 2, 3])  # type: ignore[arg-type]
