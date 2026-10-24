from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor

import energy_dash.features.forecasting.evaluation as evaluation_mod
import energy_dash.features.forecasting.predictor as predictor_mod
from energy_dash.features.forecasting.dataset import (
    get_start_end_date,
    transform_data_for_model,
)
from energy_dash.features.forecasting.evaluation import evaluate_forecasts
from energy_dash.features.forecasting.features import (
    ALL_COLUMNS,
    DEMAND,
    EXCHANGE,
    FEATURES_VERSION,
    PV,
    TARGET,
    WIND,
)
from energy_dash.features.forecasting.metrics import compute_metrics
from energy_dash.features.forecasting.predictor import (
    load_champion_model,
    run_daily_forecast,
    validate_inputs,
)


def _build_raw_db_dataframe(start_utc: str = "2026-09-15 00:00", days: int = 30) -> pd.DataFrame:
    """Tworzy syntetyczny DataFrame imitujący wynik zapytania z widoku v_energy_summary."""
    periods = days * 24
    idx = pd.date_range(start_utc, periods=periods, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "datetime_utc": idx,
            TARGET: np.linspace(250.0, 550.0, periods),
            DEMAND: np.full(periods, 19000.0),
            PV: np.full(periods, 1500.0),
            WIND: np.full(periods, 2500.0),
            EXCHANGE: np.full(periods, 200.0),
        }
    )
    # Dla ostatniej doby (jutro - D+1) cena rzeczywista TARGET jeszcze nie istnieje (NaN),
    # ale prognozy fundamentalne PSE już są:
    df.loc[df.index[-24:], TARGET] = np.nan
    return df


# ---------------------------------------------------------------------------
# 1. Testy dataset.py (okna dat i transformacja danych pod model)
# ---------------------------------------------------------------------------


def test_get_start_end_date_regular_and_dst():
    """Sprawdza wyznaczanie przedziałów czasowych dla zwykłej doby (24h) oraz zmiany czasu (25h)."""
    today = pd.Timestamp("2026-10-19 08:30:00", tz="Europe/Warsaw")
    s_train, e_train, s_pred, e_pred = get_start_end_date(window_size=30, today=today)

    assert str(s_train.tz) == "UTC"
    assert e_train == s_pred
    assert int((e_pred - s_pred) / pd.Timedelta(hours=1)) == 24

    # Dzień przed zmianą czasu na zimowy (2026-10-24 -> jutro 2026-10-25 ma 25 godzin!)
    today_dst = pd.Timestamp("2026-10-24 09:00:00", tz="Europe/Warsaw")
    _, _, s_pred_dst, e_pred_dst = get_start_end_date(window_size=30, today=today_dst)
    assert int((e_pred_dst - s_pred_dst) / pd.Timedelta(hours=1)) == 25


def test_transform_data_for_model_keeps_tomorrow_target_despite_nan_price():
    """
    Kluczowy test domenowy: na dobę D+1 kolumna TARGET (fixing_1_pln_mwh) ma wartości NaN,
    ale target_set musi zachować wszystkie 24 godziny, bo potrzebuje tylko ALL_COLUMNS (w tym price_lag_24 z dziś).
    """
    today = pd.Timestamp("2026-10-13 08:00:00", tz="Europe/Warsaw")
    s_train, e_train, s_pred, e_pred = get_start_end_date(window_size=25, today=today)

    raw_df = _build_raw_db_dataframe(start_utc="2026-09-15 00:00", days=30)
    # Ustawiamy NaN na dobę predykcji (2026-10-14 czasu lokalnego)
    raw_df.loc[(raw_df["datetime_utc"] >= s_pred) & (raw_df["datetime_utc"] < e_pred), TARGET] = (
        np.nan
    )

    target_set, train_set, y_train = transform_data_for_model(
        raw_df, s_train, e_train, s_pred, e_pred
    )

    assert len(target_set) == 24
    assert not target_set[ALL_COLUMNS].isna().any().any()
    assert len(train_set) == len(y_train)
    assert not y_train.isna().any()


# ---------------------------------------------------------------------------
# 2. Testy walidacji wejścia i integracji z MLflow w predictor.py
# ---------------------------------------------------------------------------


def test_validate_inputs_checks():
    """Weryfikuje walidację liczby godzin, braków w cechach oraz minimalnej liczby dób treningowych."""
    today = pd.Timestamp("2026-10-13 08:00:00", tz="Europe/Warsaw")
    s_train, e_train, s_pred, e_pred = get_start_end_date(window_size=25, today=today)
    raw_df = _build_raw_db_dataframe(start_utc="2026-09-15 00:00", days=30)
    target_set, train_set, _ = transform_data_for_model(raw_df, s_train, e_train, s_pred, e_pred)

    # Poprawne dane przechodzą bez wyjątku
    validate_inputs(target_set, train_set, expected_hours=24)

    # 1. Zła liczba godzin w target_set
    with pytest.raises(ValueError, match="oczekiwano 24"):
        validate_inputs(target_set.iloc[:20], train_set, expected_hours=24)

    # 2. Brakujące wartości (NaN) w zmiennych objaśniających na jutro
    bad_target = target_set.copy()
    bad_target.iloc[0, bad_target.columns.get_loc(DEMAND)] = np.nan
    with pytest.raises(ValueError, match="Braki w zmiennych na jutro"):
        validate_inputs(bad_target, train_set, expected_hours=24)

    # 3. Za mało dób treningowych (< 20)
    short_train = train_set.iloc[: 5 * 24]
    with pytest.raises(ValueError, match="Za mało dób treningowych"):
        validate_inputs(target_set, short_train, expected_hours=24)


def test_load_champion_model_validations(monkeypatch):
    """Sprawdza walidację tagów features_version, run_id i sygnatury kolumn modelu z MLflow."""
    mock_client = MagicMock()
    monkeypatch.setattr(predictor_mod, "MlflowClient", lambda: mock_client)

    # Przypadek 1: brak run_id
    mock_client.get_model_version_by_alias.return_value = SimpleNamespace(version="3", run_id=None)
    with pytest.raises(ValueError, match="Nie znaleziono run_id"):
        load_champion_model()

    # Przypadek 2: niezgodna wersja cech (features_version)
    mock_client.get_model_version_by_alias.return_value = SimpleNamespace(
        version="3", run_id="run-123"
    )
    mock_client.get_run.return_value = SimpleNamespace(
        data=SimpleNamespace(tags={"features_version": "999"})
    )
    with pytest.raises(RuntimeError, match="Niezgodna wersja cech"):
        load_champion_model()

    # Przypadek 3: niezgodna lista kolumn w sygnaturze modelu
    mock_client.get_run.return_value = SimpleNamespace(
        data=SimpleNamespace(tags={"features_version": FEATURES_VERSION})
    )
    mock_info = MagicMock()
    mock_info.signature.inputs.input_names.return_value = ["tylko_jedna_kolumna"]
    monkeypatch.setattr(predictor_mod.mlflow.models, "get_model_info", lambda uri: mock_info)

    with pytest.raises(RuntimeError, match="Kolumny modelu != ALL_COLUMNS"):
        load_champion_model()

    # Przypadek 4: wszystko zgodne -> zwraca obiekt wersji modelu
    mock_info.signature.inputs.input_names.return_value = list(ALL_COLUMNS)
    mv = load_champion_model()
    assert mv.version == "3"
    assert mv.run_id == "run-123"


def test_run_daily_forecast_dry_run_and_full(monkeypatch):
    """Testuje pełny przebieg run_daily_forecast (dry_run, skip przy istniejącej prognozie oraz zapis)."""
    today = pd.Timestamp("2026-10-13 08:00:00", tz="Europe/Warsaw")
    raw_df = _build_raw_db_dataframe(start_utc="2026-09-15 00:00", days=30)

    import mlflow.sklearn

    monkeypatch.setattr(predictor_mod, "init_mlflow", lambda: None)
    monkeypatch.setattr(
        predictor_mod,
        "load_champion_model",
        lambda: SimpleNamespace(version="4", run_id="run-abc"),
    )
    monkeypatch.setattr(predictor_mod, "get_data_from_db", lambda q, p: raw_df)
    monkeypatch.setattr(
        mlflow.sklearn,
        "load_model",
        lambda uri: DummyRegressor(strategy="mean"),
    )

    # A. Gdy prognoza już istnieje i dry_run=False -> zwraca None (pomija)
    monkeypatch.setattr(predictor_mod, "forecast_exists", lambda *args: True)
    assert run_daily_forecast(today=today, dry_run=False) is None

    # B. Gdy dry_run=True -> liczy prognozę na 24h i zwraca Series bez zapisu do bazy
    saved_calls = []
    monkeypatch.setattr(
        predictor_mod,
        "save_forecasts",
        lambda preds, mv, run_id: saved_calls.append((preds, mv, run_id)),
    )
    preds = run_daily_forecast(today=today, dry_run=True)
    assert isinstance(preds, pd.Series)
    assert len(preds) == 24
    assert len(saved_calls) == 0

    # C. Gdy dry_run=False i prognozy jeszcze nie ma -> loguje run i zapisuje w bazie
    monkeypatch.setattr(predictor_mod, "forecast_exists", lambda *args: False)
    monkeypatch.setattr(predictor_mod, "log_prod_run", lambda *args: "prod-run-99")
    preds_full = run_daily_forecast(today=today, dry_run=False)
    assert len(preds_full) == 24
    assert len(saved_calls) == 1
    assert saved_calls[0][1] == "4"
    assert saved_calls[0][2] == "prod-run-99"


# ---------------------------------------------------------------------------
# 3. Testy ewaluacji prognoz (evaluation.py)
# ---------------------------------------------------------------------------


def test_compute_metrics_values_and_peak_hours():
    """Weryfikuje poprawność wyliczania metryk MAE, RMSE, WAPE, Bias, Peak oraz rMAE."""
    # Tworzymy 24 godziny w strefie UTC odpowiadające dobie lokalnej
    idx = pd.date_range("2026-10-20 00:00", periods=24, freq="h", tz="Europe/Warsaw").tz_convert(
        "UTC"
    )
    y_true = pd.Series(np.full(24, 400.0), index=idx)
    y_pred = pd.Series(np.full(24, 420.0), index=idx)  # stały błąd +20 PLN/MWh
    y_b0 = pd.Series(np.full(24, 360.0), index=idx)  # błąd naiwny 40 PLN/MWh

    metrics = compute_metrics(y_true, y_pred, y_b0)

    assert metrics["mae"] == pytest.approx(20.0)
    assert metrics["rmse"] == pytest.approx(20.0)
    assert metrics["bias"] == pytest.approx(20.0)
    assert metrics["wape"] == pytest.approx(20.0 / 400.0)
    assert metrics["mae_peak"] == pytest.approx(20.0)
    assert metrics["bias_peak"] == pytest.approx(20.0)
    assert metrics["rmae"] == pytest.approx(0.5)  # 20 / 40 = 0.5
    assert metrics["n_obs"] == 24.0


def test_evaluate_forecasts_workflow(monkeypatch):
    """Sprawdza logowanie metryk do MLflow dla kompletnych dób i pomijanie niekompletnych."""
    monkeypatch.setattr(evaluation_mod, "init_mlflow", lambda: None)

    mock_client = MagicMock()
    mock_client.get_run.return_value = SimpleNamespace(data=SimpleNamespace(tags={}))
    monkeypatch.setattr(evaluation_mod, "MlflowClient", lambda: mock_client)

    idx = pd.date_range("2026-10-18 00:00", periods=24, freq="h", tz="UTC")
    df_complete = pd.DataFrame(
        {
            "datetime_utc": idx,
            "model_version": "3",
            "mlflow_run_id": "run-ready",
            "forecast_pln_mwh": 350.0,
            "actual": 340.0,
            "b0": 320.0,
        }
    )
    df_incomplete = pd.DataFrame(
        {
            "datetime_utc": idx,
            "model_version": "3",
            "mlflow_run_id": "run-missing-actual",
            "forecast_pln_mwh": 350.0,
            "actual": np.nan,
            "b0": 320.0,
        }
    )
    combined_df = pd.concat([df_complete, df_incomplete], ignore_index=True)

    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    monkeypatch.setattr(evaluation_mod, "engine", mock_engine)
    monkeypatch.setattr(evaluation_mod.pd, "read_sql_query", lambda *a, **kw: combined_df)

    n_evaluated = evaluate_forecasts(days_back=4)

    assert n_evaluated == 1
    mock_client.set_tag.assert_called_once_with("run-ready", "evaluated", "true")
    assert mock_client.log_metric.call_count >= 6


# ---------------------------------------------------------------------------
# 3. Test zmiany czasu na letni/zimowy
# ---------------------------------------------------------------------------


def test_transform_data_for_model_dst_transition():
    """Weryfikuje poprawność generowania target_set dla doby 25-godzinnej (zmiana czasu)."""
    today_dst = pd.Timestamp("2026-10-24 09:00:00", tz="Europe/Warsaw")
    s_train, e_train, s_pred, e_pred = get_start_end_date(window_size=30, today=today_dst)

    # Generujemy pełny ciąg godzin od s_train do e_pred (25 godzin dla doby predykcji)
    idx = pd.date_range(s_train, e_pred, freq="h", tz="UTC", inclusive="left")
    raw_df = pd.DataFrame(
        {
            "datetime_utc": idx,
            TARGET: np.linspace(250.0, 550.0, len(idx)),
            DEMAND: np.full(len(idx), 19000.0),
            PV: np.full(len(idx), 1500.0),
            WIND: np.full(len(idx), 2500.0),
            EXCHANGE: np.full(len(idx), 200.0),
        }
    )
    raw_df.loc[raw_df["datetime_utc"] >= s_pred, TARGET] = np.nan

    target_set, train_set, y_train = transform_data_for_model(
        raw_df, s_train, e_train, s_pred, e_pred
    )

    assert len(target_set) == 25
    assert not target_set[ALL_COLUMNS].isna().any().any()


def test_transform_data_for_model_dst_spring_23h():
    """Weryfikuje poprawność generowania target_set dla doby wiosennej 23-godzinnej (zmiana na czas letni)."""
    today_spring = pd.Timestamp("2026-03-28 09:00:00", tz="Europe/Warsaw")
    s_train, e_train, s_pred, e_pred = get_start_end_date(window_size=30, today=today_spring)

    assert int((e_pred - s_pred) / pd.Timedelta(hours=1)) == 23

    idx = pd.date_range(s_train, e_pred, freq="h", tz="UTC", inclusive="left")
    raw_df = pd.DataFrame(
        {
            "datetime_utc": idx,
            TARGET: np.linspace(250.0, 550.0, len(idx)),
            DEMAND: np.full(len(idx), 19000.0),
            PV: np.full(len(idx), 1500.0),
            WIND: np.full(len(idx), 2500.0),
            EXCHANGE: np.full(len(idx), 200.0),
        }
    )
    raw_df.loc[raw_df["datetime_utc"] >= s_pred, TARGET] = np.nan

    target_set, train_set, y_train = transform_data_for_model(
        raw_df, s_train, e_train, s_pred, e_pred
    )

    assert len(target_set) == 23
    assert not target_set[ALL_COLUMNS].isna().any().any()


def test_transform_data_for_model_day_after_spring_dst():
    """
    Weryfikuje generowanie cech w poniedziałek po wiośnie (24h),
    gdy w dobie D-1 (niedziela) brakowało godziny 02:00.
    """
    today_post_spring = pd.Timestamp("2026-03-29 09:00:00", tz="Europe/Warsaw")
    s_train, e_train, s_pred, e_pred = get_start_end_date(window_size=30, today=today_post_spring)

    assert int((e_pred - s_pred) / pd.Timedelta(hours=1)) == 24

    idx = pd.date_range(s_train, e_pred, freq="h", tz="UTC", inclusive="left")
    raw_df = pd.DataFrame(
        {
            "datetime_utc": idx,
            TARGET: np.linspace(250.0, 550.0, len(idx)),
            DEMAND: np.full(len(idx), 19000.0),
            PV: np.full(len(idx), 1500.0),
            WIND: np.full(len(idx), 2500.0),
            EXCHANGE: np.full(len(idx), 200.0),
        }
    )
    raw_df.loc[raw_df["datetime_utc"] >= s_pred, TARGET] = np.nan

    target_set, train_set, y_train = transform_data_for_model(
        raw_df, s_train, e_train, s_pred, e_pred
    )

    assert len(target_set) == 24
    assert not target_set[ALL_COLUMNS].isna().any().any()
