from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Vendor Onboarding Platform"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://vendor:vendor@localhost:5432/vendor_onboarding"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
