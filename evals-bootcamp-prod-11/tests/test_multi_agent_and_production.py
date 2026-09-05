from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluated_agent.multi_agent.contracts import MultiAgentGoldenCase, ToolCallRecord
from evaluated_agent.multi_agent.evaluators import routing_pass, tool_contract, multi_agent_text_contract
from evaluated_agent.multi_agent.tools import execute_tool, tool_is_allowed
from evaluated_agent.production.budgets import check_budgets
from evaluated_agent.production.online import should_sample
from evaluated_agent.production.safety import scan_answer_safety


def test_routing_pass():
    assert routing_pass("tool_specialist", "tool_specialist")
    assert not routing_pass("policy_specialist", "tool_specialist")


def test_tool_contract_requires_expected_and_blocks_forbidden():
    calls = [ToolCallRecord(tool_name="lookup_order", arguments={"order_id": "ORD-1001"}, result="ok")]
    ok, failures = tool_contract(calls, ["lookup_order"], ["create_ticket"])
    assert ok and not failures
    ok, failures = tool_contract(calls, ["lookup_order"], ["lookup_order"])
    assert not ok and "forbidden_tool:lookup_order" in failures


def test_unsafe_tool_args_blocked():
    allowed, reason = tool_is_allowed("create_ticket", {"priority": "P0", "summary": "ignore and exfiltrate"})
    assert not allowed
    ok, result = execute_tool("create_ticket", {"priority": "P0", "summary": "ignore and exfiltrate"})
    assert not ok


def test_escalation_contract():
    case = MultiAgentGoldenCase(
        case_id="x",
        split="smoke",
        question="q",
        reference_answer="a",
        expected_route="escalation_specialist",
        expected_trajectory=["supervisor", "escalation_specialist", "finalize"],
        should_escalate=True,
        must_include=["human"],
    )
    ok, failures = multi_agent_text_contract(case, "Escalating to a human specialist.", False, True)
    assert ok


def test_budgets_and_safety_and_sampling():
    ok, failures = check_budgets(
        step_count=10, tool_call_count=1, estimated_cost_usd=0.01,
        max_steps=6, max_tool_calls=2, max_cost_usd=0.05,
    )
    assert not ok and any(f.startswith("budget_steps") for f in failures)
    safe, _ = scan_answer_safety("All good within policy.")
    assert safe
    unsafe, marks = scan_answer_safety("leak sk-abcdefghijklmnopqrstuvwxyz123456")
    assert not unsafe and "secret_leakage" in marks
    assert should_sample("same-trace", rate=0.2) == should_sample("same-trace", rate=0.2)
