from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://agent:agent@postgres:5432/agent_service"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    api_base_url: str = "http://localhost:8000"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    demo_tenant: str = "tenant_acme"
    demo_user: str = "user_42"
    idempotency_ttl_hours: int = 24
    outbox_poll_seconds: float = 1.0
    outbox_claim_timeout_seconds: int = 30
    allow_demo_faults: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
