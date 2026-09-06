"""Declared tool catalog."""

from app.governance.schemas import ActionClass, TargetSystem, ToolDefinition

_TOOLS: dict[str, ToolDefinition] = {
    "deploy_catalog.get_architecture_context": ToolDefinition(
        tool_name="deploy_catalog.get_architecture_context",
        action_class=ActionClass.READ,
        target_system=TargetSystem.DEPLOY_CATALOG,
        default_policy="allow",
        allowed_fields=["architecture", "components", "runtime_mapping"],
        description="Read deployment architecture context (mock catalog — no real SaaS).",
    ),
    "openai.generate_answer": ToolDefinition(
        tool_name="openai.generate_answer",
        action_class=ActionClass.READ,
        target_system=TargetSystem.OPENAI,
        default_policy="allow_with_policy",
        allowed_fields=["query", "context", "model"],
        blocked_fields=["api_key", "password", "token"],
        description="Generate an answer via OpenAI — real API, governed gateway path.",
    ),
}


def get_tool(tool_name: str) -> ToolDefinition | None:
    return _TOOLS.get(tool_name)


def list_tools() -> list[ToolDefinition]:
    return list(_TOOLS.values())


def is_known_tool(tool_name: str) -> bool:
    return tool_name in _TOOLS
