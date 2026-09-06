"""Mock deployment catalog."""

from app.governance.schemas import JITToken, ProposedAction, ToolResult

_ARCHITECTURE = {
    "architecture": "FastAPI API + Celery worker + Redis",
    "components": [
        "FastAPI API on ECS Fargate behind ALB",
        "Celery worker on ECS Fargate (no ALB)",
        "Redis on ElastiCache",
        "Secrets Manager for REDIS_URL and OPENAI_API_KEY",
        "CloudWatch for api/worker logs",
    ],
    "runtime_mapping": {
        "local": "docker-compose",
        "aws": "ECR + ECS Fargate + ElastiCache + ALB",
    },
}


def get_architecture_context(action: ProposedAction, jit_token: JITToken) -> ToolResult:
    scoped = {key: _ARCHITECTURE[key] for key in jit_token.allowed_fields if key in _ARCHITECTURE}
    return ToolResult(
        success=True,
        status="executed",
        tool_name=action.tool_name,
        message="Deployment context retrieved from mock catalog",
        data=scoped,
    )
