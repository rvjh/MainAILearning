from __future__ import annotations

from obs_agent.cost.budgets import check_budgets
from obs_agent.cost.pricing import estimate_chat_cost_usd


def test_cost_estimate():
    cost = estimate_chat_cost_usd(1_000_000, 1_000_000, input_per_1m=0.15, output_per_1m=0.60)
    assert abs(cost - 0.75) < 1e-9


def test_budget_breach():
    ok, failures = check_budgets(
        step_count=10,
        tool_call_count=9,
        estimated_cost_usd=1.0,
        execution_ms=100,
        max_steps=8,
        max_tool_calls=4,
        max_cost_usd=0.02,
    )
    assert ok is False
    assert any(f.startswith("budget_steps") for f in failures)
    assert any(f.startswith("budget_tools") for f in failures)
    assert any(f.startswith("budget_cost") for f in failures)
