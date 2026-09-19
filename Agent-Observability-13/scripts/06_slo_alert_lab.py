#!/usr/bin/env python3
"""SLO + alert lab: trigger actionable alert, identify runs, follow runbook."""

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

    # Enough volume for rate-based alert; mix of bad quality + stuck work.
    for _ in range(4):
        rt.run(
            RunRequest(
                question="What is the status of ORD-1001?",
                scenario=FaultScenario.CONFIDENTLY_WRONG,
            )
        )
    rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.STUCK_HEARTBEAT,
        )
    )
    # One good run so eligible >= 5
    rt.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.CORRECT,
        )
    )

    report = rt.slo_report()
    out = ROOT / "reports" / "slo_alerts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report["slo"], indent=2))
    print(f"alerts fired: {len(report['alerts'])}")
    for alert in report["alerts"]:
        print(f"\n- [{alert['severity']}] {alert['name']}: {alert['message']}")
        print(f"  affected: {alert['affected_job_ids']}")
        print("  runbook steps:")
        for step in alert["runbook"]["steps"]:
            print(f"    {step}")

    assert report["slo"]["breached"] is True
    assert any(a["name"] == "slo_burn_validated_latency" for a in report["alerts"])
    assert any(a["name"] == "unresolved_or_overdue_jobs" for a in report["alerts"])
    print(f"\nwrote {out}")
    print("slo alert lab: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
