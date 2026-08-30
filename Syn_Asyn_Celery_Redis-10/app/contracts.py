from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


TERMINAL = {
    JobStatus.CANCELLED,
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.DEAD_LETTERED,
}

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.ACCEPTED: {JobStatus.QUEUED, JobStatus.CANCEL_REQUESTED},
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED},
    JobStatus.RUNNING: {
        JobStatus.SUCCEEDED,
        JobStatus.RETRYING,
        JobStatus.CANCEL_REQUESTED,
        JobStatus.FAILED,
        JobStatus.DEAD_LETTERED,
    },
    JobStatus.RETRYING: {JobStatus.QUEUED, JobStatus.CANCEL_REQUESTED, JobStatus.DEAD_LETTERED},
    JobStatus.CANCEL_REQUESTED: {JobStatus.CANCELLED},
}


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    user_id: str
    request_id: str = ""


@dataclass(frozen=True)
class CreateJobCommand:
    prompt: str
    thread_id: str
    max_attempts: int = 3
    metadata: dict[str, str] = field(default_factory=dict)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt.strip(),
            "thread_id": self.thread_id,
            "max_attempts": self.max_attempts,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass
class JobRecord:
    job_id: str
    tenant_id: str
    user_id: str
    idempotency_key: str
    request_hash: str
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    checkpoint_index: int
    cancel_requested: bool
    next_retry_delay: float | None
    result: dict[str, Any] | None
    error: str | None
    version: int
    created_at: str
    updated_at: str

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("request_hash", None)
        data.pop("idempotency_key", None)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class JobEvent:
    cursor: int
    job_id: str
    tenant_id: str
    event_type: str
    status: JobStatus
    detail: dict[str, Any]
    created_at: str
