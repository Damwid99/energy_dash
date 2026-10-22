# src/energy_dash/features/forecasting/metrics.py
import numpy as np
import pandas as pd

from energy_dash.core.timeutils import to_local_tz

DEFAULT_PEAK_HOURS: tuple[int, ...] = (18, 19, 20, 21)


def compute_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    y_b0: pd.Series | None = None,
    peak_hours: tuple[int, ...] = DEFAULT_PEAK_HOURS,
) -> dict[str, float]:
    """Oblicza metryki jakości prognozy (MAE, RMSE, WAPE, BIAS, rMAE).

    Czysta funkcja - brak zależności od bazy danych, MLflow czy configu.
    """
    err = y_pred - y_true
    abs_err = err.abs()

    peak = np.isin(to_local_tz(y_true).index.hour, peak_hours)

    m = {
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "wape": float(abs_err.sum() / y_true.abs().sum()),
        "bias": float(err.mean()),
        "mae_peak": float(abs_err[peak].mean()) if peak.any() else np.nan,
        "bias_peak": float(err[peak].mean()) if peak.any() else np.nan,
        "n_obs": float(len(y_true)),
    }

    if y_b0 is not None and y_b0.notna().all():
        base_mae = float((y_b0 - y_true).abs().mean())
        if base_mae > 0:
            m["rmae"] = m["mae"] / base_mae

    return {k: v for k, v in m.items() if not np.isnan(v)}
