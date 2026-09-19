from __future__ import annotations

import re
from typing import Any

from obs_agent.contracts import ToolCallRecord, ValidationResult
from obs_agent.tools import ALLOWED_TOOLS


def validate_output(
    *,
    answer: str,
    citations: list[str],
    tool_calls: list[ToolCallRecord],
    require_citation: bool = True,
) -> ValidationResult:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    non_empty = bool(answer and answer.strip())
    checks["non_empty_answer"] = non_empty
    if not non_empty:
        failures.append("empty_answer")

    schema_ok = len(answer) <= 2000 and "\x00" not in answer
    checks["schema_ok"] = schema_ok
    if not schema_ok:
        failures.append("schema_invalid")

    citation_ok = (not require_citation) or bool(citations)
    checks["has_citation"] = citation_ok
    if require_citation and not citations:
        failures.append("missing_citation")

    tools_ok = all(tc.name in ALLOWED_TOOLS for tc in tool_calls)
    checks["allowed_tools_only"] = tools_ok
    if not tools_ok:
        failures.append("disallowed_tool")

    args_ok = all(not _bad_args(tc.arguments) for tc in tool_calls)
    checks["safe_arguments"] = args_ok
    if not args_ok:
        failures.append("unsafe_tool_arguments")

    return ValidationResult(ok=not failures, checks=checks, failures=failures)


def _bad_args(arguments: dict[str, Any]) -> bool:
    blob = " ".join(str(v) for v in arguments.values()).lower()
    return any(m in blob for m in ("ignore previous", "bypass", "exfiltrate", "api_key"))


CLAIM_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def check_groundedness(*, answer: str, evidence: list[str]) -> tuple[bool, list[str]]:
    """Deterministic groundedness: dates/status words must appear in evidence."""
    failures: list[str] = []
    joined = " ".join(evidence).lower()
    answer_l = answer.lower()

    for date in CLAIM_DATE.findall(answer):
        if date not in joined:
            failures.append(f"ungrounded_date:{date}")

    # Hallucinated delivery language without tool evidence.
    if "delivered on" in answer_l or "will arrive tomorrow" in answer_l:
        if "delivered" not in joined and "eta=" not in joined:
            failures.append("ungrounded_delivery_claim")

    if "refund approved" in answer_l and "refund" not in joined:
        failures.append("ungrounded_refund_claim")

    return not failures, failures


def check_business_outcome(
    *,
    question: str,
    answer: str,
    tool_calls: list[ToolCallRecord],
    grounded: bool,
    validation_ok: bool,
) -> bool:
    if not validation_ok or not grounded:
        return False
    q = question.lower()
    if "status" in q or "where is" in q or "track" in q:
        used_lookup = any(tc.name == "lookup_order" and tc.ok for tc in tool_calls)
        return used_lookup and ("status=" in " ".join(tc.output for tc in tool_calls if tc.ok) or "status" in answer.lower())
    if "refund" in q:
        return "refund" in answer.lower() and grounded
    if "ticket" in q:
        return any(tc.name == "create_ticket" and tc.ok for tc in tool_calls)
    return grounded and validation_ok
