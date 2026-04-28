from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: Literal["dev", "prod"] = "dev"
    secret_key: str | None = None
    database_url: str = "sqlite:///./site.db"
    admin_username: str | None = None
    admin_password: str | None = None
    session_max_age: int = 60 * 60 * 24 * 7

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
