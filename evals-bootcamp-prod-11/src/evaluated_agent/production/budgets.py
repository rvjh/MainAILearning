from __future__ import annotations


def check_budgets(
    *,
    step_count: int,
    tool_call_count: int,
    estimated_cost_usd: float,
    max_steps: int,
    max_tool_calls: int,
    max_cost_usd: float,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if step_count > max_steps:
        failures.append(f"budget_steps:{step_count}>{max_steps}")
    if tool_call_count > max_tool_calls:
        failures.append(f"budget_tools:{tool_call_count}>{max_tool_calls}")
    if estimated_cost_usd > max_cost_usd:
        failures.append(f"budget_cost:{estimated_cost_usd:.4f}>{max_cost_usd}")
    return not failures, failures
