from datetime import date, timedelta

import mlflow
import pandas as pd
from sklearn.base import clone

from src.ml.fix_I_forecast.dataset import (
    QUERY,
    WARSAW_TZ,
    get_data_from_db,
    get_start_end_date,
    transform_data_for_model,
)
from src.ml.fix_I_forecast.features import ALL_COLUMNS, FEATURES_VERSION, TARGET
from src.ml.fix_I_forecast.predictor import (
    MODEL_NAME,
    WINDOW_DAYS,
    init_mlflow,
    load_champion_model,
    save_forecasts,
    validate_inputs,
)

BACKFILL_EXPERIMENT = "da_price_fixing1_backfill"


def _log_backfill_day(day, mv, train_set, preds: pd.Series) -> str:
    with mlflow.start_run(run_name=f"backfill_{day}") as run:
        mlflow.set_tags(
            {
                "kind": "backfill",
                "delivery_date": str(day),
                "model_version": str(mv.version),
                "features_version": FEATURES_VERSION,
            }
        )
        mlflow.log_params(
            {
                "train_start": str(train_set.index.min()),
                "train_end": str(train_set.index.max()),
                "n_train_rows": len(train_set),
                "n_train_days": train_set["delivery_date"].nunique(),
            }
        )
        mlflow.log_text(preds.rename("forecast").to_csv(), "forecast.csv")
        return run.info.run_id


def backfill_forecasts(first_day: date, last_day: date, dry_run: bool = False) -> pd.Series:
    """Odtwarza prognozy na doby first_day..last_day (włącznie), tak jakby powstały dzień wcześniej."""
    init_mlflow()
    mlflow.set_experiment(BACKFILL_EXPERIMENT)
    mv = load_champion_model()
    recipe = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{mv.version}")

    def window_for(day) -> tuple:
        today = (pd.Timestamp(day) - pd.Timedelta(days=1)).tz_localize(WARSAW_TZ)
        return get_start_end_date(WINDOW_DAYS, today)

    # jedno zapytanie na cały zakres
    data_start = window_for(first_day)[0]
    data_end = window_for(last_day)[3]
    df = get_data_from_db(QUERY, {"start_date": data_start, "end_date": data_end})

    parts = []
    for day in pd.date_range(first_day, last_day, freq="D"):
        s_train, e_train, s_pred, e_pred = window_for(day)
        expected_hours = int((e_pred - s_pred) / pd.Timedelta(hours=1))
        try:
            target_set, train_set, _ = transform_data_for_model(
                df, s_train, e_train, s_pred, e_pred
            )
            validate_inputs(target_set, train_set, expected_hours)
        except ValueError as e:
            print(f"[BACKFILL] {day.date()}: pomijam ({e})")
            continue
        model = clone(recipe).fit(train_set[ALL_COLUMNS], train_set[TARGET])
        day_preds = pd.Series(model.predict(target_set[ALL_COLUMNS]), index=target_set.index)
        parts.append(day_preds)
        if not dry_run:
            run_id = _log_backfill_day(day.date(), mv, train_set, day_preds)
            save_forecasts(day_preds, mv.version, run_id)
        print(f"[BACKFILL] {day.date()}: ok ...")

    return pd.concat(parts)


if __name__ == "__main__":
    today = pd.Timestamp.now(tz=WARSAW_TZ).date()
    backfill_forecasts(today - timedelta(days=30), today)
    from src.ml.fix_I_forecast.evaluation import evaluate_forecasts

    evaluate_forecasts(days_back=45)
