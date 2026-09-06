"""Policy decisions for proposed actions."""

from app.governance.schemas import (
    ActionClass,
    AgentContext,
    PolicyDecision,
    PolicyDecisionType,
    ProposedAction,
)
from app.governance.tool_registry import get_tool, is_known_tool


def _ttl_for_action_class(action_class: ActionClass) -> int:
    return {
        ActionClass.READ: 300,
        ActionClass.WRITE: 180,
        ActionClass.HIGH_RISK_WRITE: 60,
        ActionClass.DESTRUCTIVE: 0,
    }.get(action_class, 180)


def _risk_score(action: ProposedAction) -> int:
    return {
        ActionClass.READ: 10,
        ActionClass.WRITE: 40,
        ActionClass.HIGH_RISK_WRITE: 75,
        ActionClass.DESTRUCTIVE: 100,
    }.get(action.action_class, 50)


def evaluate_policy(action: ProposedAction, context: AgentContext) -> PolicyDecision:
    if not is_known_tool(action.tool_name):
        return PolicyDecision(
            decision=PolicyDecisionType.DENY,
            reason="Unknown tool",
            risk_score=100,
            ttl_seconds=0,
        )

    tool = get_tool(action.tool_name)
    assert tool is not None
    risk = _risk_score(action)
    ttl = _ttl_for_action_class(tool.action_class)

    if tool.action_class == ActionClass.DESTRUCTIVE:
        return PolicyDecision(
            decision=PolicyDecisionType.DENY,
            reason="Destructive action denied by default",
            risk_score=100,
            ttl_seconds=0,
        )

    if context.data_classification in ("pii_high", "financial_high"):
        return PolicyDecision(
            decision=PolicyDecisionType.REQUIRE_APPROVAL,
            reason=f"Data classification '{context.data_classification}' requires approval",
            risk_score=risk,
            required_approval_type="security_officer",
            allowed_scope=tool.allowed_fields,
            ttl_seconds=ttl,
        )

    if not context.user_role:
        return PolicyDecision(
            decision=PolicyDecisionType.DENY,
            reason="Action denied — no user role",
            risk_score=risk,
            ttl_seconds=0,
        )

    return PolicyDecision(
        decision=PolicyDecisionType.ALLOW,
        reason="Read action allowed with scoped JIT",
        risk_score=risk,
        allowed_scope=tool.allowed_fields,
        ttl_seconds=ttl,
    )
