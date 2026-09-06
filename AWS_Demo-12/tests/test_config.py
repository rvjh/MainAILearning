"""Config tests — REDIS_URL and defaults."""

from app.config import Settings


def test_redis_url_default():
    settings = Settings(_env_file=None)
    assert settings.REDIS_URL == "redis://redis:6379/0"


def test_redis_url_override(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://custom-host:6379/1")
    settings = Settings(_env_file=None)
    assert settings.REDIS_URL == "redis://custom-host:6379/1"
