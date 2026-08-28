from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_path: Path = Path("./data/db/zipp.sqlite3")
    backup_path: Path = Path("./data/backups")
    public_url: str = ""
    debug: bool = False
    backup_retention: int = 30
    session_secret: str = "development-only-change-me"
    session_cookie_secure: bool = False
    session_max_age: int = 604800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("session_secret", mode="before")
    @classmethod
    def use_safe_development_default_for_blank_secret(cls, value):
        return value or "development-only-change-me"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.resolve().as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
