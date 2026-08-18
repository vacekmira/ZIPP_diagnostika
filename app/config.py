from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_path: Path = Path("./data/db/zipp.sqlite3")
    backup_path: Path = Path("./data/backups")
    public_url: str = ""
    debug: bool = False
    backup_retention: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.resolve().as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
