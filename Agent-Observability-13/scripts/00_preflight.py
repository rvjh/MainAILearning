#!/usr/bin/env python3
"""Preflight: imports, .env load, deterministic/LLM run check."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.config import get_settings, load_env
from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime


def main() -> int:
    env_path = load_env(override=True)
    settings = get_settings(reload=True)
    print("=== Observability session preflight ===")
    print(f"env_file={settings.env_file}")
    print(f"env_loaded_from={env_path}")
    print(f"agent_version={settings.agent_version}")
    print(f"prompt_version={settings.prompt_version}")
    print(f"deployment_version={settings.deployment_version}")
    print(f"allow_demo_faults={settings.allow_demo_faults}")
    print(f"openai_configured={settings.use_llm}")
    print(f"openai_model={settings.openai_model}")
    print(f"openai_key_chars={len(settings.openai_api_key)}")
    print(f"langsmith_tracing={settings.langsmith_tracing}")
    print(f"langsmith_project={settings.langsmith_project}")
    print(f"langsmith_key_chars={len(settings.langsmith_api_key)}")

    if not settings.use_llm:
        print("NOTE: OPENAI_API_KEY missing — using deterministic answers")

    rt = ObservabilityRuntime(settings=settings, export_traces=False, sleep_fn=lambda _s: None)
    result = rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.CORRECT,
        )
    )
    assert result.status.value == "completed", result
    assert result.business_success, result
    assert result.health and result.health.quality, result.health
    provider = result.versions.get("model", "?")
    print("correct run: OK")
    print(f"  job_id={result.job_id} trace_id={result.trace_id}")
    print(f"  model/provider={provider}")
    print(f"  answer={result.answer[:160]}")
    if result.errors:
        print(f"  errors={result.errors}")
    print("preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
