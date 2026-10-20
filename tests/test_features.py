import numpy as np
import pandas as pd

from src.ml.fix_I_forecast.features import (
    ALL_COLUMNS,
    DEMAND,
    EXCHANGE,
    PV,
    TARGET,
    WIND,
    make_training_frame,
)


def test_make_training_frame_shape_and_columns():
    """Smoke test: tworzy mały syntetyczny DataFrame i sprawdza pipeline transformacji cech."""
    periods = 200
    dates = pd.date_range("2026-08-01 00:00", periods=periods, freq="h", tz="UTC")

    synthetic_raw = pd.DataFrame(
        {
            TARGET: np.random.uniform(200.0, 600.0, size=periods),
            DEMAND: np.random.uniform(15000.0, 22000.0, size=periods),
            PV: np.random.uniform(0.0, 8000.0, size=periods),
            WIND: np.random.uniform(500.0, 5000.0, size=periods),
            EXCHANGE: np.random.uniform(-1000.0, 1000.0, size=periods),
        },
        index=dates,
    )

    df_feats = make_training_frame(synthetic_raw, dropna=False)

    assert not df_feats.empty
    assert len(df_feats) == periods

    for col in ALL_COLUMNS:
        assert col in df_feats.columns, f"Brakująca wyliczona kolumna: {col}"

    assert TARGET in df_feats.columns


def test_make_training_frame_dropna():
    """Weryfikuje poprawne odrzucenie wierszy NaN wynikających z opóźnień (lags)."""
    periods = 200
    dates = pd.date_range("2026-08-01 00:00", periods=periods, freq="h", tz="UTC")

    synthetic_raw = pd.DataFrame(
        {
            TARGET: np.full(periods, 300.0),
            DEMAND: np.full(periods, 18000.0),
            PV: np.full(periods, 1000.0),
            WIND: np.full(periods, 2000.0),
            EXCHANGE: np.full(periods, 0.0),
        },
        index=dates,
    )

    df_cleaned = make_training_frame(synthetic_raw, dropna=True)

    assert len(df_cleaned) == periods - 24
    assert not df_cleaned[ALL_COLUMNS].isna().any().any()
