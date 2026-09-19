#!/usr/bin/env python3
"""Cost lab: run that succeeds but violates efficiency budget."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime


def main() -> int:
    rt = ObservabilityRuntime(export_traces=True, sleep_fn=lambda _s: None)

    looped = rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.TOOL_LOOP,
        )
    )
    oversized = rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.OVERSIZED_CONTEXT,
        )
    )
    breach = rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.BUDGET_BREACH_SUCCESS,
        )
    )

    for label, result in (
        ("tool_loop", looped),
        ("oversized_context", oversized),
        ("budget_breach_success", breach),
    ):
        print(f"\n=== {label} ===")
        print(
            json.dumps(
                {
                    "status": result.status.value,
                    "business_success": result.business_success,
                    "tool_calls": len(result.tool_calls),
                    "prompt_tokens": result.prompt_tokens,
                    "cost_usd": result.estimated_cost_usd,
                    "budget_ok": result.budget_ok,
                    "budget_failures": result.budget_failures,
                    "efficiency": result.health.efficiency if result.health else None,
                },
                indent=2,
            )
        )

    assert looped.status.value == "completed"
    assert not looped.budget_ok
    assert not oversized.budget_ok
    assert breach.status.value == "completed"
    assert not breach.budget_ok
    print(
        "\nDiscussion: If completion rate improved but cost/successful-task doubled, "
        "did the release improve the system?"
    )
    print("cost lab: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
