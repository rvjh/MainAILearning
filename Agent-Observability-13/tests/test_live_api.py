"""Live API smoke tests — require OPENAI_API_KEY in Session-Observability/.env.

Run:
  pytest -m live -q
Skip automatically when no key is configured.
"""

from __future__ import annotations

import os

import pytest

from obs_agent.config import get_settings, load_env
from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_settings():
    load_env(override=True)
    settings = get_settings(reload=True)
    if not settings.use_llm:
        pytest.skip("OPENAI_API_KEY not set in .env — skipping live API tests")
    return settings


@pytest.fixture
def live_runtime(live_settings):
    return ObservabilityRuntime(
        settings=live_settings,
        export_traces=True,
        sleep_fn=lambda _s: None,
    )


def test_env_loads_real_openai_key(live_settings):
    assert live_settings.openai_api_key
    assert live_settings.openai_model
    assert os.getenv("OPENAI_API_KEY", "").strip() == live_settings.openai_api_key


def test_live_correct_run_uses_model(live_runtime, live_settings):
    result = live_runtime.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.CORRECT,
        )
    )
    assert result.status.value == "completed"
    assert result.business_success is True
    assert result.grounded is True
    assert result.health and result.health.quality is True
    assert result.versions.get("model") == live_settings.openai_model
    assert "shipped" in result.answer.lower() or "ORD-1001" in result.answer
    assert not any(str(e).startswith("model_fallback:") for e in result.errors), result.errors


def test_live_wrong_run_still_deterministic_and_fails_quality(live_runtime):
    """Fault scenarios must stay deterministic even with API keys present."""
    result = live_runtime.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.CONFIDENTLY_WRONG,
        )
    )
    assert result.status.value == "completed"
    assert result.grounded is False
    assert result.business_success is False
    assert "2026-12-25" in result.answer
