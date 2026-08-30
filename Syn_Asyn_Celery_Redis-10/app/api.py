"""Thin FastAPI adapter — real HTTP contract for the Sunday production demo."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.contracts import AuthContext, CreateJobCommand
from app.errors import IdempotencyConflict, InvalidRequest, InvalidTransition, JobNotFound
from app.service import AgentJobService

service = AgentJobService()
app = FastAPI(title="Sunday Production Agent Service", version="1.0.0")


class CreateJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    thread_id: str
    max_attempts: int = 3
    metadata: dict[str, str] = Field(default_factory=dict)


@app.exception_handler(InvalidRequest)
def invalid_request_handler(_request: Request, exc: InvalidRequest):
    return JSONResponse({"type": "invalid_request", "detail": str(exc)}, status_code=400)


@app.exception_handler(IdempotencyConflict)
def idempotency_handler(_request: Request, exc: IdempotencyConflict):
    return JSONResponse({"type": "idempotency_conflict", "detail": str(exc)}, status_code=422)


@app.exception_handler(JobNotFound)
def not_found_handler(_request: Request, exc: JobNotFound):
    return JSONResponse({"type": "not_found", "detail": str(exc)}, status_code=404)


@app.exception_handler(InvalidTransition)
def transition_handler(_request: Request, exc: InvalidTransition):
    return JSONResponse({"type": "invalid_transition", "detail": str(exc)}, status_code=409)


def verified_auth(request: Request) -> AuthContext:
    """Classroom verifier. Production replaces with verified OIDC/JWT claims."""
    tenant = request.headers.get("X-Demo-Tenant")
    user = request.headers.get("X-Demo-User")
    if not tenant or not user:
        raise HTTPException(401, "verified authentication context required")
    return AuthContext(tenant_id=tenant, user_id=user, request_id=request.headers.get("X-Request-ID", ""))


@app.post("/v1/agent-jobs", status_code=202)
def create_job(
    body: CreateJobBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    auth: AuthContext = Depends(verified_auth),
):
    response = service.create_job(
        CreateJobCommand(**body.model_dump()),
        auth=auth,
        idempotency_key=idempotency_key,
    )
    return JSONResponse(response["body"], status_code=response["status_code"], headers=response["headers"])


@app.get("/v1/agent-jobs/{job_id}")
def get_job(job_id: str, auth: AuthContext = Depends(verified_auth)):
    return service.get_job(job_id, auth=auth)["body"]


@app.delete("/v1/agent-jobs/{job_id}", status_code=202)
def cancel_job(job_id: str, auth: AuthContext = Depends(verified_auth)):
    response = service.cancel_job(job_id, auth=auth)
    return JSONResponse(response["body"], status_code=response["status_code"])


@app.get("/v1/agent-jobs/{job_id}/events")
def events(
    job_id: str,
    last_event_id: int = Header(0, alias="Last-Event-ID"),
    auth: AuthContext = Depends(verified_auth),
):
    return StreamingResponse(
        service.event_stream(job_id, auth=auth, after_cursor=last_event_id),
        media_type="text/event-stream",
    )


@app.get("/health/live")
def live():
    return service.live()["body"]


@app.get("/health/ready")
def ready():
    response = service.ready()
    return JSONResponse(response["body"], status_code=response["status_code"])


@app.get("/")
def root():
    return {
        "service": "Sunday Production Working Demo",
        "truth": "PostgreSQL job record",
        "delivery": "Redis + Celery via transactional outbox",
        "agent": "LangGraph + LangChain ChatOpenAI",
        "memory": "Governed gateway (model proposes, policy decides)",
    }
