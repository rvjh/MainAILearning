"""Tool Gateway — policy, JIT, execute, audit for every worker tool call."""

from __future__ import annotations

import time
from collections.abc import Callable

from app.governance.audit_log import record_audit_event
from app.governance.human_approval import request_approval
from app.governance.jit_access import mint_jit_token
from app.governance.policy_engine import evaluate_policy
from app.governance.schemas import (
    AgentContext,
    AuditStatus,
    PolicyDecisionType,
    ProposedAction,
    ToolResult,
)
from app.governance.tool_registry import is_known_tool
from app.tools.deploy_catalog_mock import get_architecture_context
from app.tools.openai_tool import generate_answer_tool

_TOOL_DISPATCH: dict[str, Callable] = {
    "deploy_catalog.get_architecture_context": get_architecture_context,
    "openai.generate_answer": generate_answer_tool,
}


def invoke_tool(action: ProposedAction, context: AgentContext) -> ToolResult:
    start = time.perf_counter()

    if not is_known_tool(action.tool_name):
        decision = evaluate_policy(action, context)
        _audit(action, context, decision, status=AuditStatus.DENIED, start=start)
        return ToolResult(
            success=False,
            status="denied",
            tool_name=action.tool_name,
            message=decision.reason,
            policy_decision=decision,
        )

    decision = evaluate_policy(action, context)

    if decision.decision == PolicyDecisionType.DENY:
        _audit(action, context, decision, status=AuditStatus.DENIED, start=start)
        return ToolResult(
            success=False,
            status="denied",
            tool_name=action.tool_name,
            message=decision.reason,
            policy_decision=decision,
        )

    approval_result = None
    if decision.decision == PolicyDecisionType.REQUIRE_APPROVAL:
        approval_result = request_approval(action, context, decision)
        if approval_result.pending:
            record_audit_event(
                agent_id=action.agent_id,
                agent_run_id=action.agent_run_id,
                user_id=action.user_id,
                tool_name=action.tool_name,
                target_system=action.target_system.value,
                action_class=action.action_class.value,
                resource_type=action.resource_type,
                resource_id=action.resource_id,
                args=action.args,
                reason=decision.reason,
                policy_decision=decision.decision.value,
                risk_score=decision.risk_score,
                approval_required=True,
                approval_id=approval_result.approval_id,
                status=AuditStatus.PENDING_APPROVAL,
                duration_ms=_elapsed_ms(start),
            )
            return ToolResult(
                success=False,
                status="pending_approval",
                tool_name=action.tool_name,
                message=approval_result.reason,
                policy_decision=decision,
            )
        if not approval_result.approved:
            _audit(
                action,
                context,
                decision,
                status=AuditStatus.DENIED,
                approval_id=approval_result.approval_id,
                start=start,
            )
            return ToolResult(
                success=False,
                status="denied",
                tool_name=action.tool_name,
                message="Approval rejected or unavailable",
                policy_decision=decision,
            )

    jit_token = mint_jit_token(action, context, decision, approval_result)
    if jit_token is None:
        _audit(action, context, decision, status=AuditStatus.DENIED, start=start, error="JIT not minted")
        return ToolResult(
            success=False,
            status="denied",
            tool_name=action.tool_name,
            message="JIT token could not be minted",
            policy_decision=decision,
        )

    handler = _TOOL_DISPATCH.get(action.tool_name)
    if handler is None:
        _audit(
            action,
            context,
            decision,
            status=AuditStatus.FAILED,
            jit_token_id=jit_token.token_id,
            start=start,
            error="No handler registered",
        )
        return ToolResult(
            success=False,
            status="failed",
            tool_name=action.tool_name,
            message="No tool handler registered",
            policy_decision=decision,
            jit_token=jit_token,
        )

    try:
        result = handler(action, jit_token)
        result.policy_decision = decision
        result.jit_token = jit_token
        record_audit_event(
            agent_id=action.agent_id,
            agent_run_id=action.agent_run_id,
            user_id=action.user_id,
            tool_name=action.tool_name,
            target_system=action.target_system.value,
            action_class=action.action_class.value,
            resource_type=action.resource_type,
            resource_id=action.resource_id,
            args=action.args,
            reason=action.reason or decision.reason,
            policy_decision=decision.decision.value,
            risk_score=decision.risk_score,
            approval_required=decision.decision == PolicyDecisionType.REQUIRE_APPROVAL,
            approval_id=approval_result.approval_id if approval_result else None,
            jit_token_id=jit_token.token_id,
            status=AuditStatus.EXECUTED,
            before=result.before,
            after=result.after,
            duration_ms=_elapsed_ms(start),
        )
        return result
    except Exception as exc:
        record_audit_event(
            agent_id=action.agent_id,
            agent_run_id=action.agent_run_id,
            user_id=action.user_id,
            tool_name=action.tool_name,
            target_system=action.target_system.value,
            action_class=action.action_class.value,
            resource_type=action.resource_type,
            resource_id=action.resource_id,
            args=action.args,
            reason=decision.reason,
            policy_decision=decision.decision.value,
            risk_score=decision.risk_score,
            jit_token_id=jit_token.token_id,
            status=AuditStatus.FAILED,
            error=str(exc),
            duration_ms=_elapsed_ms(start),
        )
        return ToolResult(
            success=False,
            status="failed",
            tool_name=action.tool_name,
            message=str(exc),
            error=str(exc),
            policy_decision=decision,
            jit_token=jit_token,
        )


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _audit(
    action: ProposedAction,
    context: AgentContext,
    decision,
    *,
    status: AuditStatus,
    approval_id: str | None = None,
    jit_token_id: str | None = None,
    start: float,
    error: str | None = None,
) -> None:
    record_audit_event(
        agent_id=action.agent_id,
        agent_run_id=action.agent_run_id,
        user_id=action.user_id,
        tool_name=action.tool_name,
        target_system=action.target_system.value,
        action_class=action.action_class.value,
        resource_type=action.resource_type,
        resource_id=action.resource_id,
        args=action.args,
        reason=decision.reason,
        policy_decision=decision.decision.value,
        risk_score=decision.risk_score,
        approval_required=decision.decision == PolicyDecisionType.REQUIRE_APPROVAL,
        approval_id=approval_id,
        jit_token_id=jit_token_id,
        status=status,
        error=error,
        duration_ms=_elapsed_ms(start),
    )
