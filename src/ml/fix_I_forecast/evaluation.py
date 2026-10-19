import numpy as np
import pandas as pd
from mlflow import MlflowClient
from sqlalchemy import text

from ml.fix_I_forecast.features import LOCAL_TZ
from ml.fix_I_forecast.predictor import init_mlflow
from src.common.database import engine

PEAK_HOURS_LOCAL = (18, 19, 20, 21)

EVAL_QUERY = text("""
WITH hourly_energy AS (
    SELECT 
        date_trunc('hour', datetime_utc) AS datetime_utc,
        AVG(fixing_1_pln_mwh) AS fixing_1_pln_mwh
    FROM energy_prices
    GROUP BY 1
)
SELECT f.datetime_utc,
       f.model_version,
       f.mlflow_run_id,
       f.forecast_pln_mwh,
       e.fixing_1_pln_mwh   AS actual,
       lag.fixing_1_pln_mwh AS b0
FROM da_price_forecasts f
LEFT JOIN hourly_energy e   ON e.datetime_utc = f.datetime_utc
LEFT JOIN hourly_energy lag ON lag.datetime_utc = f.datetime_utc - INTERVAL '24 hours'
WHERE f.datetime_utc >= :start
ORDER BY f.datetime_utc;
""")


def compute_metrics(
    y_true: pd.Series, y_pred: pd.Series, y_b0: pd.Series | None = None
) -> dict[str, float]:
    err = y_pred - y_true
    abs_err = err.abs()
    peak = np.isin(y_true.index.tz_convert(LOCAL_TZ).hour, PEAK_HOURS_LOCAL)

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
        m["rmae"] = m["mae"] / float((y_b0 - y_true).abs().mean())
    return {k: v for k, v in m.items() if not np.isnan(v)}


def evaluate_forecasts(days_back: int = 7) -> int:
    """Dopisuje metryki do runów, których prognozy mają już komplet fixingów."""
    init_mlflow()
    client = MlflowClient()
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back)

    with engine.connect() as conn:
        df = pd.read_sql_query(EVAL_QUERY, conn, params={"start": start})
    if df.empty:
        return 0
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)

    n_done = 0
    for (run_id, mv), g in df.dropna(subset=["mlflow_run_id"]).groupby(
        ["mlflow_run_id", "model_version"]
    ):
        if g["actual"].isna().any():
            print(
                f"[EVAL] Run {run_id}: brak fixingu dla {int(g['actual'].isna().sum())} godzin, pomijam."
            )
            continue
        try:
            if client.get_run(run_id).data.tags.get("evaluated") == "true":
                continue
            g = g.set_index("datetime_utc")
            metrics = compute_metrics(g["actual"], g["forecast_pln_mwh"], g["b0"])
            for k, v in metrics.items():
                client.log_metric(run_id, k, v)
            client.set_tag(run_id, "evaluated", "true")
            n_done += 1
        except Exception as e:  # jeden zły run nie może zatrzymać reszty
            print(f"[EVAL] Run {run_id} (model v{mv}): {e}")
    return n_done
