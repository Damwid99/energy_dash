# src/energy_dash/features/forecasting/evaluation.py
import pandas as pd
from mlflow import MlflowClient
from sqlalchemy import text

from energy_dash.core.db import engine
from energy_dash.core.settings import get_settings
from energy_dash.features.forecasting.metrics import compute_metrics
from energy_dash.features.forecasting.predictor import init_mlflow

settings = get_settings()

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
LEFT JOIN hourly_energy lag 
    ON (lag.datetime_utc AT TIME ZONE 'Europe/Warsaw')::date = (f.datetime_utc AT TIME ZONE 'Europe/Warsaw')::date - 1
   AND EXTRACT(HOUR FROM lag.datetime_utc AT TIME ZONE 'Europe/Warsaw') = EXTRACT(HOUR FROM f.datetime_utc AT TIME ZONE 'Europe/Warsaw')WHERE f.datetime_utc >= :start
ORDER BY f.datetime_utc;
""")


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

            metrics = compute_metrics(
                y_true=g["actual"],
                y_pred=g["forecast_pln_mwh"],
                y_b0=g["b0"],
                peak_hours=settings.forecast.peak_hours_local,
            )

            for k, v in metrics.items():
                client.log_metric(run_id, k, v)
            client.set_tag(run_id, "evaluated", "true")
            n_done += 1
        except Exception as e:
            print(f"[EVAL] Run {run_id} (model v{mv}): {e}")

    return n_done
