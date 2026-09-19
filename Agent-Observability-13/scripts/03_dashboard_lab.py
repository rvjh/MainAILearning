#!/usr/bin/env python3
"""Dashboard lab: answer Are users affected? / Where is delay? / Which version?"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.config import get_settings
from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime


def main() -> int:
    base = get_settings()
    rt = ObservabilityRuntime(
        settings=base,
        export_traces=True,
        sleep_fn=lambda _s: None,
    )

    # v1 traffic
    for scenario in (
        FaultScenario.CORRECT,
        FaultScenario.CORRECT,
        FaultScenario.SLOW_TOOL,
    ):
        rt.run(RunRequest(question="What is the status of ORD-1001?", scenario=scenario))

    # v2 traffic with a quality regression
    rt.settings = replace(base, agent_version="support-ops-v2")
    rt.agent.settings = rt.settings
    for scenario in (FaultScenario.CONFIDENTLY_WRONG, FaultScenario.TRANSIENT_TOOL_ERROR):
        rt.run(RunRequest(question="What is the status of ORD-1001?", scenario=scenario))

    dash = rt.dashboard()
    out = ROOT / "reports" / "dashboard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dash, indent=2), encoding="utf-8")

    jobs = dash["jobs"]
    latency = dash["latency_ms"]["end_to_end"]
    print("1) Are users affected?")
    print(
        f"   completed={jobs['completed']} failed={jobs['failed']} overdue={jobs['overdue']} "
        f"validated_success={dash['quality']['validated_success']} "
        f"validated_failure={dash['quality']['validated_failure']}"
    )
    print("2) Where is the delay?")
    print(
        f"   e2e p50={latency.get('p50', 0):.0f}ms p95={latency.get('p95', 0):.0f}ms"
    )
    print(
        f"   queue={dash['latency_ms']['queue_wait']} exec={dash['latency_ms']['execution']}"
    )
    print("3) Which version is affected?")
    print(f"   version counters: {json.dumps(dash['versions'], indent=2)}")
    print(f"wrote {out}")
    assert jobs["completed"] >= 4
    assert dash["quality"]["validated_failure"] >= 1
    print("dashboard lab: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
