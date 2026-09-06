"""HITL approval hook (mock)."""

from app.governance.schemas import (
    AgentContext,
    ApprovalResult,
    PolicyDecision,
    PolicyDecisionType,
    ProposedAction,
)


def request_approval(
    action: ProposedAction,
    context: AgentContext,
    decision: PolicyDecision,
) -> ApprovalResult:
    if decision.decision == PolicyDecisionType.DENY:
        return ApprovalResult(approved=False, pending=False, reason="Cannot approve a denied action")

    if action.args.get("approval_simulated") is True:
        return ApprovalResult(
            approved=True,
            pending=False,
            approval_id=f"APPR-SIM-{action.action_id[:8]}",
            approver="platform_engineer_demo",
            reason="Simulated approval for teaching demo",
        )

    return ApprovalResult(
        approved=False,
        pending=True,
        approval_id=f"APPR-PEND-{action.action_id[:8]}",
        reason="Awaiting human approval",
    )
