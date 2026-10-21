from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore")
    user: str = "energy_user"
    password: SecretStr
    host: str = "localhost"
    port: int = 5458
    db: str = "energy_db"

    @property
    def url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.db}"


class MlflowSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MLFLOW_", env_file=".env", extra="ignore")
    tracking_uri: str = "http://localhost:5000"
    model_name: str = "da_price_fixing1"
    model_alias: str = "champion"
    prod_experiment: str = "da_price_fixing1_prod"


class ForecastSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORECAST_", env_file=".env", extra="ignore")
    window_days: int = 365
    min_train_days: int = 20
    peak_hours_local: tuple[int, ...] = (18, 19, 20, 21)


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")
    api_base: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_API_BASE")
    model: str = "ollama_chat/gpt-oss:20b-cloud"
    use_response_format: bool = True


class NewsSettings(BaseSettings):
    titles_limit: int = Field(default=100, validation_alias="NEWS_TITLES_LIMIT")
    select_max: int = Field(default=15, validation_alias="NEWS_SELECT_MAX")
    body_max_chars: int = Field(default=4000, validation_alias="NEWS_BODY_MAX_CHARS")


class SchedulerSettings(BaseSettings):
    news_hour: int = 7
    tge_publish_hour: int = 14


class Settings(BaseModel):
    tz: ZoneInfo = ZoneInfo("Europe/Warsaw")
    db: DataBaseSettings = DataBaseSettings()  # type: ignore
    mlflow: MlflowSettings = MlflowSettings()
    forecast: ForecastSettings = ForecastSettings()
    llm: LlmSettings = LlmSettings()
    news: NewsSettings = NewsSettings()
    scheduler: SchedulerSettings = SchedulerSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
