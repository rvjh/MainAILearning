from __future__ import annotations

from obs_agent.contracts import FaultScenario, RunRequest


def test_opening_contrast(runtime):
    q = "What is the status of order ORD-1001?"
    good = runtime.run(RunRequest(question=q, scenario=FaultScenario.CORRECT))
    bad = runtime.run(RunRequest(question=q, scenario=FaultScenario.CONFIDENTLY_WRONG))
    assert good.status.value == "completed" and bad.status.value == "completed"
    assert good.business_success and good.health.quality
    assert not bad.business_success and not bad.health.quality


def test_dashboard_three_questions(runtime):
    for scenario in (
        FaultScenario.CORRECT,
        FaultScenario.SLOW_TOOL,
        FaultScenario.CONFIDENTLY_WRONG,
        FaultScenario.OVERSIZED_CONTEXT,
    ):
        runtime.run(RunRequest(question="What is the status of ORD-1001?", scenario=scenario))
    dash = runtime.dashboard()
    assert dash["jobs"]["completed"] == 4
    assert dash["quality"]["validated_failure"] >= 1
    assert dash["latency_ms"]["end_to_end"]["count"] == 4


def test_cost_success_but_budget_fail(runtime):
    result = runtime.run(
        RunRequest(
            question="What is the status of ORD-1001?",
            scenario=FaultScenario.BUDGET_BREACH_SUCCESS,
        )
    )
    assert result.status.value == "completed"
    assert result.budget_ok is False
    assert result.health and result.health.efficiency is False


def test_ids_present_on_every_run(runtime):
    result = runtime.run(
        RunRequest(question="What is the status of ORD-1001?", scenario=FaultScenario.CORRECT)
    )
    assert result.job_id.startswith("job_")
    assert result.request_id.startswith("req_")
    assert result.attempt_id.startswith("attempt_")
    assert result.trace_id.startswith("trace_")
    assert result.versions["agent_version"]
