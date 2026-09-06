"""Job schema and agent workflow tests — gateway mocked, no live OpenAI."""

from unittest.mock import patch

from app.schemas import JobRequest, JobStatusResponse, JobSubmittedResponse
from app.tasks import WORKFLOW_STEPS, build_result, execute_agent_workflow, validate_answer


def test_job_request_schema_accepts_query():
    req = JobRequest(query="Explain ECS Fargate deployment")
    assert req.query == "Explain ECS Fargate deployment"


def test_job_submitted_response_shape():
    resp = JobSubmittedResponse(job_id="abc-123", status_url="/jobs/abc-123")
    data = resp.model_dump()
    assert data["job_id"] == "abc-123"
    assert data["status_url"] == "/jobs/abc-123"


def test_job_status_response_shape():
    resp = JobStatusResponse(
        job_id="abc-123",
        status="completed",
        progress=None,
        result={"answer": "done"},
    )
    data = resp.model_dump()
    assert data["job_id"] == "abc-123"
    assert data["status"] == "completed"
    assert data["result"]["answer"] == "done"


def test_build_result_includes_governance():
    result = build_result(
        "deployment architecture",
        "Real LLM answer",
        "gpt-4o-mini",
        context_data={"architecture": "FastAPI + Celery"},
        tools_invoked=["deploy_catalog.get_architecture_context", "openai.generate_answer"],
    )
    assert result["query"] == "deployment architecture"
    assert result["governance"]["tools_invoked"] == [
        "deploy_catalog.get_architecture_context",
        "openai.generate_answer",
    ]
    assert result["steps_completed"] == WORKFLOW_STEPS


def test_validate_answer_rejects_empty():
    try:
        validate_answer("short")
        assert False, "expected ValueError"
    except ValueError:
        pass


@patch("app.tasks.invoke_tool")
def test_execute_agent_workflow_uses_gateway(mock_invoke):
    from app.governance.schemas import ToolResult

    mock_invoke.side_effect = [
        ToolResult(
            success=True,
            status="executed",
            tool_name="deploy_catalog.get_architecture_context",
            data={"architecture": "FastAPI + Celery + Redis"},
        ),
        ToolResult(
            success=True,
            status="executed",
            tool_name="openai.generate_answer",
            data={"answer": "This is a governed OpenAI response for the class demo."},
        ),
    ]

    result = execute_agent_workflow("What is Celery?", "job-123", step_delay_seconds=0)
    assert result["provider"] == "openai"
    assert "governed OpenAI" in result["answer"]
    assert mock_invoke.call_count == 2
