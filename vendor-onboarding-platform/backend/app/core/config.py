from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Vendor Onboarding Platform"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://vendor:vendor@localhost:5432/vendor_onboarding"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = DEV_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Documents
    upload_dir: str = "uploads"
    max_upload_mb: int = 10

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @model_validator(mode="after")
    def _require_real_secret_outside_dev(self) -> "Settings":
        if self.environment not in {"local", "test"} and self.secret_key == DEV_SECRET_KEY:
            raise ValueError("SECRET_KEY must be set when ENVIRONMENT is not local/test")
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
