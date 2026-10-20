import mlflow
import pandas as pd
from mlflow import MlflowClient
from sklearn.base import clone
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from src.common.database import engine
from src.common.timeutils import to_local_tz
from src.config.settings import get_settings
from src.ml.fix_I_forecast.dataset import (
    QUERY,
    get_data_from_db,
    get_start_end_date,
    transform_data_for_model,
)
from src.ml.fix_I_forecast.features import ALL_COLUMNS, FEATURES_VERSION, TARGET
from src.models_db.forecasts import DAPriceForecast

settings = get_settings()

LOCAL_TZ = settings.tz
MODEL_NAME = settings.mlflow.model_name
MODEL_ALIAS = settings.mlflow.model_alias
PROD_EXPERIMENT = settings.mlflow.prod_experiment
WINDOW_DAYS = settings.forecast.window_days
MIN_TRAIN_DAYS = settings.forecast.min_train_days

MLFLOW_TRACKING_URI = settings.mlflow.tracking_uri


def init_mlflow():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(PROD_EXPERIMENT)


def load_champion_model():
    """
    Pobiera model @champion z MLflow
    """
    client = MlflowClient()

    mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
    run_id = mv.run_id
    if not run_id:
        raise ValueError("Nie znaleziono run_id dla modelu!")
    run_tags = client.get_run(run_id).data.tags
    model_features_version = run_tags.get("features_version")
    if model_features_version != FEATURES_VERSION:
        raise RuntimeError(
            f"Niezgodna wersja cech: model= {model_features_version}, kod={FEATURES_VERSION}"
        )
    cols = mlflow.models.get_model_info(
        f"models:/{MODEL_NAME}/{mv.version}"
    ).signature.inputs.input_names()
    if set(cols) != set(ALL_COLUMNS):
        raise RuntimeError(f"Kolumny modelu != ALL_COLUMNS: {set(cols) ^ set(ALL_COLUMNS)}")
    return mv


def forecast_exists(start_predict, end_predict, model_version, expected_hours) -> bool:
    stmt = (
        select(func.count())
        .select_from(DAPriceForecast)
        .where(
            DAPriceForecast.datetime_utc >= start_predict,
            DAPriceForecast.datetime_utc < end_predict,
            DAPriceForecast.model_version == str(model_version),
        )
    )

    with engine.connect() as conn:
        return conn.execute(stmt).scalar() >= expected_hours


def validate_inputs(target_set: pd.DataFrame, train_set: pd.DataFrame, expected_hours: int):
    if len(target_set) != expected_hours:
        raise ValueError(f"Jutro ma {len(target_set)} godzin w danych, oczekiwano {expected_hours}")
    missing = target_set[ALL_COLUMNS].isna().sum()
    missing = missing[missing > 0]
    if not missing.empty:
        raise ValueError(f"Braki w zmiennych na jutro: {missing.to_dict()}")
    n_days = train_set["delivery_date"].nunique()
    if n_days < MIN_TRAIN_DAYS:
        raise ValueError(f"Za mało dób treningowych: {n_days}")


def log_prod_run(target_date, mv, train_set, preds: pd.Series) -> str:
    with mlflow.start_run(run_name=f"prod_{target_date}") as run:
        mlflow.set_tags(
            {
                "delivery_date": str(target_date),
                "model_version": str(mv.version),
                "features_version": FEATURES_VERSION,
            }
        )

        mlflow.log_params(
            {
                "train_start": train_set.index.min(),
                "train_end": str(train_set.index.max()),
                "n_train_rows": len(train_set),
            }
        )
        mlflow.log_text(preds.rename("forecast").to_csv(), "forecast.csv")
        return run.info.run_id


def save_forecasts(preds: pd.Series, model_version, run_id: str | None):
    rows = [
        {
            "datetime_utc": ts.to_pydatetime(),
            "model_version": str(model_version),
            "forecast_pln_mwh": float(p),
            "mlflow_run_id": run_id,
        }
        for ts, p in preds.items()
    ]

    stmt = insert(DAPriceForecast).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["datetime_utc", "model_version"],
        set_={
            "forecast_pln_mwh": stmt.excluded.forecast_pln_mwh,
            "mlflow_run_id": stmt.excluded.mlflow_run_id,
            "created_at_utc": func.now(),
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def run_daily_forecast(today: pd.Timestamp | None = None, dry_run: bool = False):
    init_mlflow()
    start_train, end_train, start_pred, end_pred = get_start_end_date(WINDOW_DAYS, today)
    expected_hours = int((end_pred - start_pred) / pd.Timedelta(hours=1))
    target_date = to_local_tz(start_pred).date()

    mv = load_champion_model()
    if not dry_run and forecast_exists(start_pred, end_pred, mv.version, expected_hours):
        print(f"[ML] Prognoza na {target_date} (model v{mv.version} już jest, pomijam)")
        return None
    df = get_data_from_db(QUERY, {"start_date": start_train, "end_date": end_pred})
    target_set, train_set, _ = transform_data_for_model(
        df, start_train, end_train, start_pred, end_pred
    )
    validate_inputs(target_set, train_set, expected_hours)
    recipe = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{mv.version}")
    model = clone(recipe).fit(train_set[ALL_COLUMNS], train_set[TARGET])
    preds = pd.Series(model.predict(target_set[ALL_COLUMNS]), index=target_set.index)
    if dry_run:
        return preds

    run_id = None
    try:
        run_id = log_prod_run(target_date, mv, train_set, preds)
    except Exception as e:
        print(f"[ML] Nie udało się zalogować runu w MLflow: {e}")
    save_forecasts(preds, mv.version, run_id)
    print(f"[ML] Zapisano prognoze na {target_date}, model v{mv.version}, {len(preds)} godzin")
    return preds


if __name__ == "__main__":
    print(
        run_daily_forecast(
            dry_run=True,
            today=pd.Timestamp(year=2026, day=13, month=10, hour=6).tz_localize(LOCAL_TZ),
        )
    )
