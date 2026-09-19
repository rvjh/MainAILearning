from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Local layout: Session-Observability/src/obs_agent/config.py → parents[2]
# Docker layout: /app/obs_agent/config.py → parents[1] == /app
_PKG = Path(__file__).resolve().parent
ROOT = _PKG.parent.parent if _PKG.parent.name == "src" else _PKG.parent


def load_env(*, override: bool = True) -> Path | None:
    """
    Load Session-Observability/.env into os.environ.

    override=True so values in .env win over empty/stale shell exports.
    Also accepts a .env in the current working directory as a fallback.
    """
    candidates = [
        ROOT / ".env",
        Path.cwd() / ".env",
        Path.cwd() / "Session-Observability" / ".env",
    ]
    loaded_from: Path | None = None
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=override)
            loaded_from = path.resolve()
            break

    _apply_langsmith_env()
    return loaded_from


def _apply_langsmith_env() -> None:
    """Map LANGSMITH_* into the LANGCHAIN_* vars the tracing SDK reads."""
    api_key = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    if not api_key:
        return

    tracing_raw = (os.getenv("LANGSMITH_TRACING") or "").strip().lower()
    if tracing_raw in {"0", "false", "no", "off"}:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGSMITH_API_KEY"] = api_key
    project = (os.getenv("LANGSMITH_PROJECT") or "july-cohort-observability").strip()
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGSMITH_PROJECT"] = project


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    langsmith_api_key: str
    langsmith_tracing: bool
    langsmith_project: str
    allow_demo_faults: bool
    agent_version: str
    prompt_version: str
    deployment_version: str
    cost_input_usd_per_1m: float
    cost_output_usd_per_1m: float
    logs_dir: Path
    reports_dir: Path
    env_file: str

    @property
    def use_llm(self) -> bool:
        return bool(self.openai_api_key)


def get_settings(*, reload: bool = False) -> Settings:
    if reload:
        get_settings_cached.cache_clear()
    return get_settings_cached()


@lru_cache(maxsize=1)
def get_settings_cached() -> Settings:
    env_path = load_env(override=True)
    api_key = os.getenv("LANGSMITH_API_KEY", "").strip()
    tracing_raw = os.getenv("LANGSMITH_TRACING", "").strip().lower()
    if api_key and tracing_raw not in {"0", "false", "no", "off"}:
        tracing = True
    else:
        tracing = tracing_raw in {"1", "true", "yes", "on"}

    faults = os.getenv("ALLOW_DEMO_FAULTS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        langsmith_api_key=api_key,
        langsmith_tracing=tracing,
        langsmith_project=os.getenv(
            "LANGSMITH_PROJECT", "july-cohort-observability"
        ).strip(),
        allow_demo_faults=faults,
        agent_version=os.getenv("OBS_AGENT_VERSION", "support-ops-v1").strip(),
        prompt_version=os.getenv("OBS_PROMPT_VERSION", "support-prompt-v3").strip(),
        deployment_version=os.getenv("OBS_DEPLOYMENT_VERSION", "local-demo-1").strip(),
        cost_input_usd_per_1m=float(os.getenv("COST_INPUT_USD_PER_1M", "0.15")),
        cost_output_usd_per_1m=float(os.getenv("COST_OUTPUT_USD_PER_1M", "0.60")),
        logs_dir=ROOT / "logs",
        reports_dir=ROOT / "reports",
        env_file=str(env_path) if env_path else "(none found)",
    )


load_env(override=True)
