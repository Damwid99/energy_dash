"""Testy integracyjne (live) połączeń z bazą PostgreSQL, MLflow oraz serwerem Ollama.

Uruchamiane domyślnie podczas `uv run pytest`.
Aby pominąć testy wymagające działających usług sieciowych, uruchom:
    SKIP_LIVE_TESTS=1 uv run pytest
"""

import os
from datetime import timedelta

import mlflow
import pandas as pd
import pytest
import requests
from mlflow import MlflowClient
from sqlalchemy import inspect, text

from energy_dash.core.db import engine
from energy_dash.core.settings import get_settings
from energy_dash.features.forecasting.features import FEATURES_VERSION
from energy_dash.features.forecasting.predictor import init_mlflow, load_champion_model
from energy_dash.features.forecasting.queries import QUERY, get_data_from_db

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_TESTS") == "1",
    reason="Pominięto testy live (ustawiono SKIP_LIVE_TESTS=1).",
)


class TestDatabaseLiveConnection:
    """Testy połączenia z bazą danych PostgreSQL i struktury schematu."""

    def test_database_select_1(self):
        with engine.connect() as conn:
            val = conn.execute(text("SELECT 1")).scalar()
            assert val == 1

    def test_database_tables_and_view_exist(self):
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        views = set(insp.get_view_names())

        expected_tables = {
            "energy_prices",
            "pse_forecasts",
            "pse_actuals",
            "da_price_forecasts",
            "news_articles",
            "news_digests",
            "renewable_farms",
            "renewable_generation",
        }
        missing_tables = expected_tables - tables
        assert not missing_tables, f"Brakujące tabele w bazie danych: {missing_tables}"
        assert "v_energy_summary" in (views | tables), (
            "Brak widoku 'v_energy_summary' w bazie danych!"
        )

    def test_query_v_energy_summary_executes(self):
        now = pd.Timestamp.now(tz="UTC")
        df = get_data_from_db(
            QUERY,
            params={"start_date": now - timedelta(days=2), "end_date": now},
        )
        assert isinstance(df, pd.DataFrame)


class TestMlflowLiveConnection:
    """Testy połączenia z serwerem MLflow i modelu champion."""

    def test_mlflow_server_reachable(self):
        settings = get_settings()
        resp = requests.get(f"{settings.mlflow.tracking_uri.rstrip('/')}/health", timeout=5)
        assert resp.status_code == 200

    def test_mlflow_champion_model_metadata_and_tags(self):
        init_mlflow()
        mv = load_champion_model()
        assert mv is not None
        assert mv.version is not None
        assert mv.run_id is not None
        run = MlflowClient().get_run(mv.run_id)
        assert run.data.tags.get("features_version") == str(FEATURES_VERSION)

    def test_mlflow_champion_model_loads_and_has_fit_predict(self):
        settings = get_settings()
        init_mlflow()
        client = MlflowClient()
        mv = client.get_model_version_by_alias(
            settings.mlflow.model_name, settings.mlflow.model_alias
        )
        model = mlflow.sklearn.load_model(f"models:/{settings.mlflow.model_name}/{mv.version}")
        assert hasattr(model, "fit") and hasattr(model, "predict")


@pytest.mark.skip(reason="Ollama jest wyłączona/opcjonalna w środowisku testowym")
class TestOllamaLiveConnection:
    """Testy połączenia z serwerem LLM (Ollama)."""

    def test_ollama_server_reachable_and_has_configured_model(self):
        settings = get_settings()
        api_base = settings.llm.api_base.rstrip("/")
        try:
            resp = requests.get(f"{api_base}/api/tags", timeout=5)
        except requests.ConnectionError as e:
            pytest.fail(
                f"Nie udało się połączyć z serwerem Ollama pod adresem '{api_base}' "
                f"(sprawdź OLLAMA_API_BASE w .env — 'http://ollama:11434' działa tylko wewnątrz sieci Dockera): {e}"
            )
        assert resp.status_code == 200, f"Ollama zwróciła kod {resp.status_code}"

        data = resp.json()
        available_models = [m.get("name", "") for m in data.get("models", [])]
        # settings.llm.model ma postać np. 'ollama/gemma4:e4b' -> nazwa w Ollamie po '/'
        expected_model = settings.llm.model.split("/", 1)[-1]
        assert any(expected_model in m for m in available_models), (
            f"Model '{expected_model}' (z {settings.llm.model}) nie jest pobrany na serwerze Ollama. "
            f"Dostępne modele: {available_models}"
        )
