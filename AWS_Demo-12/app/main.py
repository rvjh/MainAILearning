from pathlib import Path

from app import logging_config  # noqa: F401

from typing import Any, Optional

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from app.celery_app import celery_app
from app.config import settings
from app.queue_metrics import get_queue_depth, metric_namespace, METRIC_NAME
from app.rate_limit import check_rate_limit
from app.schemas import JobRequest, JobStatusResponse, JobSubmittedResponse
from app.tasks import run_agent_job

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="AWS Agent Deployment Demo",
    description="FastAPI + Celery API — local Docker Compose maps to ECS Fargate.",
    version="1.0.0",
)

CELERY_STATUS = {
    "PENDING": "queued",
    "STARTED": "running",
    "PROGRESS": "running",
    "SUCCESS": "completed",
    "FAILURE": "failed",
    "REVOKED": "cancelled",
}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.SERVICE_NAME, "env": settings.APP_ENV}


@app.get("/metrics/queue")
def queue_metrics() -> dict[str, object]:
    return {
        "queue_depth": get_queue_depth(),
        "namespace": metric_namespace(),
        "metric_name": METRIC_NAME,
    }


@app.get("/costs")
def cost_and_limits() -> dict[str, object]:
    return {
        "rate_limit": {
            "enabled": settings.RATE_LIMIT_PER_MINUTE > 0,
            "requests_per_minute": settings.RATE_LIMIT_PER_MINUTE,
            "window_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
        },
        "openai_model": settings.OPENAI_MODEL,
        "notes": "OpenAI usage is billed per token on the worker path only.",
    }


@app.post("/jobs", response_model=JobSubmittedResponse, status_code=202)
def submit_job(body: JobRequest, request: Request) -> JobSubmittedResponse:
    check_rate_limit(
        request,
        limit=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    task = run_agent_job.apply_async(args=[body.query])
    return JobSubmittedResponse(job_id=task.id, status_url=f"/jobs/{task.id}")


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    result = AsyncResult(job_id, app=celery_app)
    status = CELERY_STATUS.get(result.state, result.state.lower())

    progress: Optional[dict[str, Any]] = None
    payload: Optional[dict[str, Any]] = None

    if result.state == "PROGRESS" and isinstance(result.info, dict):
        progress = result.info
    elif result.state == "SUCCESS":
        payload = result.result if isinstance(result.result, dict) else {"value": result.result}
    elif result.state == "FAILURE":
        raise HTTPException(status_code=500, detail=f"Job failed: {result.info}")

    return JobStatusResponse(
        job_id=job_id,
        status=status,
        progress=progress,
        result=payload,
    )
