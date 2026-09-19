from __future__ import annotations

from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.slo import ClassroomSLO, evaluate_alerts, follow_runbook


def test_slo_breach_and_alerts(runtime):
    for _ in range(4):
        runtime.run(
            RunRequest(
                question="What is the status of ORD-1001?",
                scenario=FaultScenario.CONFIDENTLY_WRONG,
            )
        )
    runtime.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.STUCK_HEARTBEAT,
        )
    )
    runtime.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.CORRECT,
        )
    )
    report = runtime.slo_report()
    assert report["slo"]["breached"] is True
    names = {a["name"] for a in report["alerts"]}
    assert "slo_burn_validated_latency" in names
    assert "unresolved_or_overdue_jobs" in names


def test_runbook_steps():
    rb = follow_runbook("runbooks/slo_validated_latency.md")
    assert rb["owner"] == "support-ops-oncall"
    assert len(rb["steps"]) >= 3


def test_classroom_slo_empty():
    result = ClassroomSLO().evaluate([])
    assert result["eligible"] == 0
    assert result["breached"] is False


def test_alert_min_volume():
    alerts = evaluate_alerts(
        runs=[
            {
                "job_id": "j1",
                "eligible": True,
                "validated_success": False,
                "end_to_end_ms": 10,
                "status": "completed",
            }
        ]
        * 3,
        slo_result={"breached": True, "eligible": 3, "ratio": 0.0},
    )
    assert not any(a.name == "slo_burn_validated_latency" for a in alerts)
