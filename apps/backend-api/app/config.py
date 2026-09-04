"""Environment-backed application settings; secret values are never defaulted."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Non-secret deployment settings plus an injected internal bearer credential."""

    model_config = SettingsConfigDict(env_prefix="BACKEND_", extra="ignore")

    app_name: str = "Product_A Backend API"
    aws_region: str = "ap-northeast-1"
    db_secret_arn: str | None = None
    internal_bearer_token: SecretStr | None = None

    @field_validator("aws_region", "db_secret_arn")
    @classmethod
    def validate_non_empty_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("configured text values must not be empty")
        return normalized

    @field_validator("internal_bearer_token")
    @classmethod
    def validate_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value():
            raise ValueError("the internal bearer token must not be empty")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings lazily so importing the package has no external side effects."""

    return Settings()
