import numpy as np
import pandas as pd
import pytest

from energy_dash.features.forecasting.features import (
    ALL_COLUMNS,
    DEMAND,
    EXCHANGE,
    PV,
    RES_SHARE,
    RESLOAD,
    TARGET,
    TIME_FEATURES,
    WIND,
    add_fundamental_features,
    add_interactions,
    add_price_lags,
    add_time_features,
    make_training_frame,
)


def _make_synthetic_raw(start: str = "2026-08-01 00:00", periods: int = 200) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            TARGET: np.linspace(100.0, 500.0, num=periods),
            DEMAND: np.full(periods, 20000.0),
            PV: np.full(periods, 2000.0),
            WIND: np.full(periods, 3000.0),
            EXCHANGE: np.full(periods, -500.0),
        },
        index=dates,
    )


def test_add_time_features_holidays_and_weekend():
    """Weryfikuje wyznaczanie cech czasowych, weekendów oraz świąt w Polsce (np. 11 listopada)."""
    # 2026-11-11 to środa (Święto Niepodległości w Polsce), 2026-11-14 to sobota
    dates = pd.to_datetime(
        ["2026-11-11 12:00:00", "2026-11-12 12:00:00", "2026-11-14 12:00:00"]
    ).tz_localize("UTC")
    df = pd.DataFrame({TARGET: [300.0, 310.0, 320.0]}, index=dates)

    res = add_time_features(df)

    for col in TIME_FEATURES:
        assert col in res.columns

    # Środa 11 listopada: nie weekend, ale święto -> is_day_off == 1.0
    assert res["is_weekend"].iloc[0] == 0.0
    assert res["is_holiday"].iloc[0] == 1.0
    assert res["is_day_off"].iloc[0] == 1.0

    # Czwartek 12 listopada: zwykły dzień roboczy -> is_day_off == 0.0
    assert res["is_weekend"].iloc[1] == 0.0
    assert res["is_holiday"].iloc[1] == 0.0
    assert res["is_day_off"].iloc[1] == 0.0

    # Sobota 14 listopada: weekend -> is_day_off == 1.0
    assert res["is_weekend"].iloc[2] == 1.0
    assert res["is_holiday"].iloc[2] == 0.0
    assert res["is_day_off"].iloc[2] == 1.0


def test_add_price_lags_24_168_and_typeday():
    """Weryfikuje opóźnienia 24h, 168h oraz logikę price_lag_typeday (Pn/So/Nd -> 168h, Wt-Pt -> 24h)."""
    df = _make_synthetic_raw(start="2026-08-01 00:00", periods=240)
    res = add_price_lags(df, df[TARGET])

    # Po 24 godzinach price_lag_24 musi równać się cenie sprzed 24h
    assert res["price_lag_24"].iloc[24] == pytest.approx(df[TARGET].iloc[0])
    # Po 168 godzinach price_lag_168 musi równać się cenie sprzed 168h
    assert res["price_lag_168"].iloc[168] == pytest.approx(df[TARGET].iloc[0])

    # Sprawdzamy typeday: dla wtorku brany jest lag_24, dla niedzieli lag_168
    local_dow = res.index.tz_convert("Europe/Warsaw").dayofweek
    for idx_pos in range(170, 240):
        if local_dow[idx_pos] in (0, 5, 6):
            assert res["price_lag_typeday"].iloc[idx_pos] == pytest.approx(
                res["price_lag_168"].iloc[idx_pos]
            )
        else:
            assert res["price_lag_typeday"].iloc[idx_pos] == pytest.approx(
                res["price_lag_24"].iloc[idx_pos]
            )


def test_add_fundamental_features_and_interactions():
    """Weryfikuje wyliczanie resload, udziału OZE (res_share) oraz cech interakcji."""
    df = _make_synthetic_raw(periods=48)
    df = add_time_features(df)
    df = add_price_lags(df, df[TARGET])
    df = add_fundamental_features(df)
    df = add_interactions(df)

    # resload = 20000 - 2000 - 3000 = 15000
    assert np.allclose(df[RESLOAD], 15000.0)
    # res_share = (2000 + 3000) / 20000 = 0.25
    assert np.allclose(df[RES_SHARE], 0.25)

    assert "lag24_x_dayoff" in df.columns
    assert "pv_x_sin_d1" in df.columns
    assert "pv_x_cos_d1" in df.columns


def test_make_training_frame_shape_and_columns():
    """Smoke test: tworzy syntetyczny DataFrame i sprawdza pełny pipeline transformacji cech."""
    synthetic_raw = _make_synthetic_raw(periods=200)
    df_feats = make_training_frame(synthetic_raw, dropna=False)

    assert not df_feats.empty
    assert len(df_feats) == 200

    for col in ALL_COLUMNS:
        assert col in df_feats.columns, f"Brakująca wyliczona kolumna: {col}"
        assert df_feats[col].dtype == np.float64

    assert TARGET in df_feats.columns


def test_make_training_frame_dropna():
    """Weryfikuje poprawne odrzucenie pierwszych 24 wierszy NaN wynikających z price_lag_24."""
    periods = 200
    synthetic_raw = _make_synthetic_raw(periods=periods)
    df_cleaned = make_training_frame(synthetic_raw, dropna=True)

    assert len(df_cleaned) == periods - 24
    assert not df_cleaned[ALL_COLUMNS].isna().any().any()
