from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_env: str = "dev"
    secret_key: str = "dev-secret-change-me"
    public_base_url: str = "http://localhost:8000"
    database_url: str = f"sqlite:///{ROOT}/data/beepbop.db"

    google_client_id: str = ""
    google_client_secret: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    gsk_project_id: str = ""

    demo_mode: bool = True
    mock_reply_seconds: int = 10
    scrape_timeout_seconds: int = 420

    @property
    def sqlite_path(self) -> Path:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url[len(prefix):])
        raise ValueError("Only sqlite:/// URLs supported")


@lru_cache
def get_settings() -> Settings:
    return Settings()
