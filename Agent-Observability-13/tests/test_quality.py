from __future__ import annotations

from obs_agent.contracts import ToolCallRecord
from obs_agent.quality.evaluators import evaluate_answer
from obs_agent.quality.online import should_sample
from obs_agent.quality.validators import check_business_outcome, validate_output


def test_unsupported_claim_fails_groundedness():
    ok, failures, _ = evaluate_answer(
        answer="Order ORD-1001 was delivered on 2026-12-25 via magic drone.",
        evidence=["order:ORD-1001 status=shipped eta=2026-09-08"],
    )
    assert ok is False
    assert any("ungrounded" in f for f in failures)


def test_validation_requires_citation():
    result = validate_output(
        answer="All good",
        citations=[],
        tool_calls=[
            ToolCallRecord(
                name="lookup_order",
                arguments={"order_id": "ORD-1001"},
                output="ok",
                ok=True,
            )
        ],
        require_citation=True,
    )
    assert result.ok is False
    assert "missing_citation" in result.failures


def test_business_outcome_needs_lookup_for_status():
    tools = [
        ToolCallRecord(
            name="lookup_order",
            arguments={"order_id": "ORD-1001"},
            output="Order ORD-1001: status=shipped",
            ok=True,
        )
    ]
    assert (
        check_business_outcome(
            question="status of ORD-1001?",
            answer="status is shipped",
            tool_calls=tools,
            grounded=True,
            validation_ok=True,
        )
        is True
    )


def test_sampling_stable():
    assert should_sample("trace-force", rate=1.0) is True
    assert should_sample("trace-force", rate=0.0) is False
    a = should_sample("stable-id-xyz", rate=0.5)
    b = should_sample("stable-id-xyz", rate=0.5)
    assert a == b
