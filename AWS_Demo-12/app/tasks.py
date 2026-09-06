"""Celery agent workflow via Tool Gateway."""

import time
from collections.abc import Callable
from typing import Any, Optional

from app.celery_app import celery_app
from app.config import settings
from app.governance.schemas import ActionClass, AgentContext, ProposedAction, TargetSystem
from app.governance.tool_gateway import invoke_tool
from app.logging_config import logger

WORKFLOW_STEPS = [
    "planning",
    "retrieving_context",
    "generating_answer",
    "validating_output",
    "completed",
]

CORE_LINE = "Agent proposes. Policy decides. Gateway executes. Audit proves."


def build_agent_context(job_id: str) -> AgentContext:
    return AgentContext(
        agent_id=settings.SERVICE_NAME,
        agent_run_id=job_id,
        user_id="bootcamp-learner",
        user_role="platform_engineer",
        environment=settings.APP_ENV,
    )


def build_result(
    query: str,
    answer: str,
    model: str,
    *,
    context_data: dict[str, Any],
    tools_invoked: list[str],
) -> dict[str, Any]:
    return {
        "query": query,
        "answer": answer,
        "context": context_data,
        "steps_completed": WORKFLOW_STEPS,
        "model": model,
        "provider": "openai",
        "governance": {
            "core_line": CORE_LINE,
            "tools_invoked": tools_invoked,
            "gateway": "tool_gateway.invoke_tool",
        },
    }


def validate_answer(answer: str) -> None:
    if not answer or len(answer.strip()) < 10:
        raise ValueError("Answer failed validation: response too short")


def execute_agent_workflow(
    query: str,
    job_id: str,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    *,
    model: str | None = None,
    step_delay_seconds: float = 0.2,
) -> dict[str, Any]:
    total_steps = len(WORKFLOW_STEPS) - 1
    chosen_model = model or settings.OPENAI_MODEL
    context = build_agent_context(job_id)
    tools_invoked: list[str] = []
    context_data: dict[str, Any] = {}
    answer = ""

    for index, step in enumerate(WORKFLOW_STEPS[:-1]):
        progress_pct = int((index / total_steps) * 100)
        if progress_callback:
            progress_callback(step, progress_pct)

        if step == "planning":
            logger.info("Planning agent job", extra={"step": step, "job_id": job_id})
            time.sleep(step_delay_seconds)

        elif step == "retrieving_context":
            action = ProposedAction(
                agent_id=context.agent_id,
                agent_run_id=context.agent_run_id,
                user_id=context.user_id,
                tool_name="deploy_catalog.get_architecture_context",
                action_class=ActionClass.READ,
                target_system=TargetSystem.DEPLOY_CATALOG,
                resource_type="architecture",
                resource_id="aws-agent-deployment-demo",
                args={"topic": query},
                reason="Retrieve deployment context before LLM call",
            )
            result = invoke_tool(action, context)
            tools_invoked.append(action.tool_name)
            if not result.success:
                raise RuntimeError(f"Gateway blocked context retrieval: {result.message}")
            context_data = result.data
            logger.info("Context retrieved via gateway", extra={"step": step, "job_id": job_id})

        elif step == "generating_answer":
            action = ProposedAction(
                agent_id=context.agent_id,
                agent_run_id=context.agent_run_id,
                user_id=context.user_id,
                tool_name="openai.generate_answer",
                action_class=ActionClass.READ,
                target_system=TargetSystem.OPENAI,
                resource_type="completion",
                resource_id=job_id,
                args={"query": query, "context": context_data, "model": chosen_model},
                reason="Generate answer after policy check and JIT mint",
            )
            result = invoke_tool(action, context)
            tools_invoked.append(action.tool_name)
            if not result.success:
                raise RuntimeError(f"Gateway blocked OpenAI call: {result.message}")
            answer = str(result.data.get("answer", ""))
            logger.info("OpenAI answer via gateway", extra={"step": step, "job_id": job_id, "model": chosen_model})

        elif step == "validating_output":
            validate_answer(answer)
            logger.info("Output validated", extra={"step": step, "job_id": job_id})
            time.sleep(step_delay_seconds)

    return build_result(
        query,
        answer,
        chosen_model,
        context_data=context_data,
        tools_invoked=tools_invoked,
    )


@celery_app.task(
    bind=True,
    name="run_agent_job",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_agent_job(self, query: str) -> dict[str, Any]:
    job_id = self.request.id or "unknown"
    logger.info("Job started", extra={"job_id": job_id})

    def on_progress(step: str, progress_pct: int) -> None:
        self.update_state(state="PROGRESS", meta={"step": step, "progress": progress_pct})

    try:
        result = execute_agent_workflow(query, job_id, progress_callback=on_progress)
        logger.info("Job completed", extra={"job_id": job_id, "model": result["model"]})
        return result
    except Exception:
        logger.exception("Job failed", extra={"job_id": job_id})
        raise
