from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
AUDIT_LOG_PATH = DATA_DIR / "audit_events.jsonl"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not AUDIT_LOG_PATH.exists():
        AUDIT_LOG_PATH.touch()


class Settings(BaseSettings):
    REDIS_URL: str = "redis://redis:6379/0"
    APP_ENV: str = "local"
    SERVICE_NAME: str = "aws-agent-deployment-demo"

    OPENAI_API_KEY: str = Field(default="", description="Local .env or ECS Secrets Manager")
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: float = 60.0
    OPENAI_MAX_TOKENS: int = 1024

    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()
