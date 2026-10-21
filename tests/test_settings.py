from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr, ValidationError

from energy_dash.core.settings import (
    DataBaseSettings,
    ForecastSettings,
    LlmSettings,
    MlflowSettings,
    NewsSettings,
    SchedulerSettings,
    Settings,
    get_settings,
)


def test_database_settings_from_env(monkeypatch):
    """Weryfikuje poprawne zaczytywanie konfiguracji bazy danych ze zmiennych środowiskowych."""
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "tajne_haslo_123")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "test_energy_db")

    db = DataBaseSettings(_env_file=None)  # type: ignore[call-arg]

    assert db.user == "test_user"
    assert isinstance(db.password, SecretStr)
    assert db.password.get_secret_value() == "tajne_haslo_123"
    assert "tajne_haslo_123" not in repr(db)
    assert db.host == "db.internal"
    assert db.port == 5433
    assert db.db == "test_energy_db"
    assert (
        db.url == "postgresql+psycopg://test_user:tajne_haslo_123@db.internal:5433/test_energy_db"
    )


def test_database_settings_missing_password_raises(monkeypatch):
    """Brak hasła POSTGRES_PASSWORD (bez pliku .env) musi rzucić czytelny ValidationError."""
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        DataBaseSettings(_env_file=None)  # type: ignore[call-arg]

    assert "password" in str(exc_info.value)


def test_mlflow_settings_defaults_and_overrides(monkeypatch):
    """Weryfikuje wartości domyślne oraz nadpisywanie zmiennych MLflow."""
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MLFLOW_MODEL_NAME", raising=False)
    monkeypatch.delenv("MLFLOW_MODEL_ALIAS", raising=False)
    monkeypatch.delenv("MLFLOW_PROD_EXPERIMENT", raising=False)

    ml_default = MlflowSettings(_env_file=None)  # type: ignore[call-arg]
    assert ml_default.tracking_uri == "http://localhost:5000"
    assert ml_default.model_name == "da_price_fixing1"
    assert ml_default.model_alias == "champion"
    assert ml_default.prod_experiment == "da_price_fixing1_prod"

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow-prod:5000")
    monkeypatch.setenv("MLFLOW_MODEL_ALIAS", "staging")
    ml_custom = MlflowSettings(_env_file=None)  # type: ignore[call-arg]
    assert ml_custom.tracking_uri == "http://mlflow-prod:5000"
    assert ml_custom.model_alias == "staging"


def test_forecast_settings_defaults_and_overrides(monkeypatch):
    """Weryfikuje ustawienia horyzontu i godzin szczytowych prognozowania."""
    fc = ForecastSettings(_env_file=None)  # type: ignore[call-arg]
    assert fc.window_days == 365
    assert fc.min_train_days == 20
    assert fc.peak_hours_local == (18, 19, 20, 21)

    monkeypatch.setenv("FORECAST_WINDOW_DAYS", "180")
    monkeypatch.setenv("FORECAST_MIN_TRAIN_DAYS", "14")
    fc_custom = ForecastSettings(_env_file=None)  # type: ignore[call-arg]
    assert fc_custom.window_days == 180
    assert fc_custom.min_train_days == 14


def test_llm_settings_defaults_and_overrides(monkeypatch):
    """Weryfikuje ustawienia modelu LLM i aliasu OLLAMA_API_BASE."""
    monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_USE_RESPONSE_FORMAT", raising=False)

    llm = LlmSettings(_env_file=None)  # type: ignore[call-arg]
    assert llm.api_base == "http://localhost:11434"
    assert llm.model == "ollama_chat/gpt-oss:20b-cloud"
    assert llm.use_response_format is True

    monkeypatch.setenv("OLLAMA_API_BASE", "http://ollama-server:11434")
    monkeypatch.setenv("LLM_MODEL", "ollama_chat/llama3:8b")
    monkeypatch.setenv("LLM_USE_RESPONSE_FORMAT", "0")
    llm_custom = LlmSettings(_env_file=None)  # type: ignore[call-arg]
    assert llm_custom.api_base == "http://ollama-server:11434"
    assert llm_custom.model == "ollama_chat/llama3:8b"
    assert llm_custom.use_response_format is False


def test_news_settings_env_overrides(monkeypatch):
    """Weryfikuje limity przetwarzania newsów przez NewsSettings."""
    monkeypatch.setenv("NEWS_TITLES_LIMIT", "50")
    monkeypatch.setenv("NEWS_SELECT_MAX", "8")
    monkeypatch.setenv("NEWS_BODY_MAX_CHARS", "2500")

    news = NewsSettings()
    assert news.titles_limit == 50
    assert news.select_max == 8
    assert news.body_max_chars == 2500


def test_news_settings_loads_from_dotenv_file(tmp_path, monkeypatch):
    """
    Sprawdza, czy NewsSettings potrafi wczytać zmienne z pliku .env,
    gdy nie są wyeksportowane bezpośrednio w os.environ.
    """
    monkeypatch.delenv("NEWS_TITLES_LIMIT", raising=False)
    monkeypatch.delenv("NEWS_SELECT_MAX", raising=False)
    monkeypatch.delenv("NEWS_BODY_MAX_CHARS", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEWS_TITLES_LIMIT=77\nNEWS_SELECT_MAX=11\nNEWS_BODY_MAX_CHARS=3333\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    news = NewsSettings()
    assert news.titles_limit == 77
    assert news.select_max == 11
    assert news.body_max_chars == 3333


def test_scheduler_settings_defaults():
    """Weryfikuje domyślne godziny zadań schedulera."""
    sched = SchedulerSettings()
    assert sched.news_hour == 7
    assert sched.tge_publish_hour == 14


def test_settings_uses_default_factory_for_subsettings(monkeypatch):
    """
    Sprawdza, czy utworzenie nowej instancji Settings() po zmianie zmiennych środowiskowych
    tworzy świeże obiekty pod-ustawień (Field(default_factory=...)), zamiast używać
    instancji utworzonych w momencie importu modułu.
    """
    monkeypatch.setenv("MLFLOW_MODEL_ALIAS", "custom_alias_xyz")
    fresh = Settings()
    assert fresh.mlflow.model_alias == "custom_alias_xyz"


def test_get_settings_singleton():
    """Weryfikuje, że get_settings() zwraca spójny obiekt Settings (singleton lru_cache)."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    assert isinstance(s1, Settings)
    assert s1.tz == ZoneInfo("Europe/Warsaw")
