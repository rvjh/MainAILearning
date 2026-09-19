#!/usr/bin/env python3
"""Opening demo: two HTTP-successful runs — one correct, one confidently wrong."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime


def _print_scorecard(label: str, result) -> None:
    h = result.health
    print(f"\n=== {label} ===")
    print(f"status={result.status.value}  (uptime dashboard would say: UP)")
    print(f"answer={result.answer}")
    print(
        "scorecard:",
        json.dumps(
            {
                "reliability": h.reliability,
                "performance": h.performance,
                "quality": h.quality,
                "efficiency": h.efficiency,
                "safety": h.safety,
                "notes": h.notes,
            },
            indent=2,
        ),
    )
    print(f"business_success={result.business_success} grounded={result.grounded}")


def main() -> int:
    rt = ObservabilityRuntime(export_traces=True, sleep_fn=lambda _s: None)
    q = "What is the status of order ORD-1001?"

    good = rt.run(RunRequest(question=q, scenario=FaultScenario.CORRECT))
    bad = rt.run(RunRequest(question=q, scenario=FaultScenario.CONFIDENTLY_WRONG))

    _print_scorecard("CORRECT run", good)
    _print_scorecard("CONFIDENTLY WRONG run", bad)

    print("\nDiscussion: Would /health or queue-depth distinguish these two?")
    print("Answer: No — both completed. Quality + business outcome did.")
    assert good.business_success and good.grounded
    assert not bad.business_success and bad.grounded is False
    print("opening demo assertions: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
