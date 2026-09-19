#!/usr/bin/env python3
"""Quality lab: unsupported claim still returns success; catch with evaluator."""

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
    result = rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.UNSUPPORTED_CLAIM,
        )
    )

    print("status:", result.status.value)
    print("answer:", result.answer)
    print("validation:", result.validation.model_dump() if result.validation else None)
    print("grounded:", result.grounded)
    print("business_success:", result.business_success)
    print("online events:", json.dumps(rt.online_events, indent=2))

    # Inspect retrieval + generation related spans
    trace = next(t for t in rt.store.traces if t["trace_id"] == result.trace_id)
    names = [s["name"] for s in trace["spans"]]
    print("span names:", names)

    assert result.status.value == "completed"
    assert result.grounded is False
    assert result.business_success is False
    assert rt.online_events, "unsupported claims should be force-sampled"
    print("quality lab: OK — convert this failure into a golden regression case next")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
