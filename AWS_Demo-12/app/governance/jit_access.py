"""Short-lived JIT tokens for tools."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.governance.schemas import (
    AgentContext,
    ApprovalResult,
    JITToken,
    PolicyDecision,
    PolicyDecisionType,
    ProposedAction,
)
from app.governance.tool_registry import get_tool


def mint_jit_token(
    action: ProposedAction,
    context: AgentContext,
    decision: PolicyDecision,
    approval_result: ApprovalResult | None = None,
) -> JITToken | None:
    if decision.decision == PolicyDecisionType.DENY:
        return None
    if decision.decision == PolicyDecisionType.REQUIRE_APPROVAL:
        if approval_result is None or not approval_result.approved:
            return None
    if decision.ttl_seconds <= 0:
        return None

    tool = get_tool(action.tool_name)
    allowed_fields = decision.allowed_scope or (tool.allowed_fields if tool else [])
    expires_at = datetime.utcnow() + timedelta(seconds=decision.ttl_seconds)

    return JITToken(
        token_value=f"jit_mock_{uuid4().hex[:12]}",
        issued_to=context.user_id,
        tool_name=action.tool_name,
        scope=[action.target_system.value],
        resource_id=action.resource_id,
        allowed_fields=allowed_fields,
        ttl_seconds=decision.ttl_seconds,
        expires_at=expires_at,
        risk_score=decision.risk_score,
    )
