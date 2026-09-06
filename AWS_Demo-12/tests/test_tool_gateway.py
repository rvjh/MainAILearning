"""Tool Gateway tests — offline, no OpenAI or Redis."""

from app.governance.schemas import ActionClass, AgentContext, ProposedAction, TargetSystem
from app.governance.tool_gateway import invoke_tool


def _context() -> AgentContext:
    return AgentContext(
        agent_id="test-agent",
        agent_run_id="run-123",
        user_id="user-123",
        user_role="platform_engineer",
    )


def test_gateway_allows_mock_catalog_read():
    action = ProposedAction(
        agent_id="test-agent",
        agent_run_id="run-123",
        user_id="user-123",
        tool_name="deploy_catalog.get_architecture_context",
        action_class=ActionClass.READ,
        target_system=TargetSystem.DEPLOY_CATALOG,
        resource_type="architecture",
        resource_id="aws-agent-deployment-demo",
        args={},
    )
    result = invoke_tool(action, _context())
    assert result.success is True
    assert result.status == "executed"
    assert "components" in result.data


def test_gateway_denies_unknown_tool():
    action = ProposedAction(
        agent_id="test-agent",
        agent_run_id="run-123",
        user_id="user-123",
        tool_name="unknown.tool",
        action_class=ActionClass.READ,
        target_system=TargetSystem.DEPLOY_CATALOG,
        resource_type="architecture",
        resource_id="x",
        args={},
    )
    result = invoke_tool(action, _context())
    assert result.success is False
    assert result.status == "denied"
