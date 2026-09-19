from __future__ import annotations


def check_budgets(
    *,
    step_count: int,
    tool_call_count: int,
    estimated_cost_usd: float,
    execution_ms: float,
    max_steps: int = 8,
    max_tool_calls: int = 4,
    max_cost_usd: float = 0.02,
    max_execution_ms: float = 5000.0,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if step_count > max_steps:
        failures.append(f"budget_steps:{step_count}>{max_steps}")
    if tool_call_count > max_tool_calls:
        failures.append(f"budget_tools:{tool_call_count}>{max_tool_calls}")
    if estimated_cost_usd > max_cost_usd:
        failures.append(f"budget_cost:{estimated_cost_usd:.4f}>{max_cost_usd}")
    if execution_ms > max_execution_ms:
        failures.append(f"budget_time_ms:{execution_ms:.0f}>{max_execution_ms}")
    return not failures, failures
