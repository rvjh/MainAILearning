"""Keep pytest offline/deterministic even when instructor .env has API keys."""

from __future__ import annotations

from dataclasses import replace

import pytest

from obs_agent.config import get_settings


@pytest.fixture
def deterministic_settings():
    return replace(
        get_settings(),
        openai_api_key="",
        langsmith_api_key="",
        langsmith_tracing=False,
    )


@pytest.fixture
def runtime(deterministic_settings):
    from obs_agent.runtime import ObservabilityRuntime

    return ObservabilityRuntime(
        settings=deterministic_settings,
        export_traces=False,
        sleep_fn=lambda _s: None,
    )
