#!/usr/bin/env python3
"""Trace lab: inject slow tool / slow model; identify bottleneck from the trace."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime


def main() -> int:
    # Real sleeps so learners see latency in the trace.
    rt = ObservabilityRuntime(export_traces=True)

    print("=== Running SLOW_TOOL scenario ===")
    slow_tool = rt.run(
        RunRequest(
            question="Where is ORD-1001?",
            scenario=FaultScenario.SLOW_TOOL,
        )
    )
    tool_bottleneck = rt.find_bottleneck(slow_tool.trace_id)
    print(json_dump(tool_bottleneck))
    assert tool_bottleneck["bottleneck"] == "tool", tool_bottleneck

    print("\n=== Running SLOW_MODEL scenario ===")
    slow_model = rt.run(
        RunRequest(
            question="Where is ORD-1001?",
            scenario=FaultScenario.SLOW_MODEL,
        )
    )
    model_bottleneck = rt.find_bottleneck(slow_model.trace_id)
    print(json_dump(model_bottleneck))
    assert model_bottleneck["bottleneck"] == "model", model_bottleneck

    print("\nIDs for whiteboard:")
    print(f"  slow_tool: job={slow_tool.job_id} trace={slow_tool.trace_id} attempt={slow_tool.attempt_id}")
    print(f"  slow_model: job={slow_model.job_id} trace={slow_model.trace_id} attempt={slow_model.attempt_id}")
    print("trace lab: OK")
    return 0


def json_dump(obj) -> str:
    import json

    return json.dumps(obj, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
