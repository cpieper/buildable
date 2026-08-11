from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/buildable.db"
    data_dir: Path = Path("./data")
    frontend_dir: Path | None = None
    session_secret: str = "development-only-change-me"
    secure_cookies: bool = False
    rebrickable_api_key: str | None = None
    initial_password: str | None = None

    model_config = SettingsConfigDict(env_prefix="BUILDABLE_", env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
