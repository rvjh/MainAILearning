"""OpenAI tool handler."""

from app.config import settings
from app.governance.schemas import JITToken, ProposedAction, ToolResult
from app.llm import generate_answer


def generate_answer_tool(action: ProposedAction, jit_token: JITToken) -> ToolResult:
    query = str(action.args.get("query", ""))
    context = str(action.args.get("context", ""))
    model = str(action.args.get("model") or settings.OPENAI_MODEL)

    enriched = f"{query}\n\nContext: {context}"
    answer = generate_answer(enriched, model=model)

    return ToolResult(
        success=True,
        status="executed",
        tool_name=action.tool_name,
        message="OpenAI answer generated via governed gateway",
        data={"answer": answer, "model": model},
    )
