from __future__ import annotations

import json
from collections.abc import Callable, Iterator

from app.contracts import AuthContext, CreateJobCommand, JobEvent, JobStatus
from app.db import ping_database
from app.errors import InvalidRequest
from app.store import PostgresJobStore


class AgentJobService:
    def __init__(
        self,
        store: PostgresJobStore | None = None,
        *,
        database_probe: Callable[[], bool] = ping_database,
        broker_probe: Callable[[], bool] | None = None,
    ) -> None:
        self.store = store or PostgresJobStore()
        self.database_probe = database_probe
        self.broker_probe = broker_probe or self._ping_redis

    def create_job(
        self,
        command: CreateJobCommand,
        *,
        auth: AuthContext,
        idempotency_key: str,
    ) -> dict:
        if not idempotency_key.strip():
            raise InvalidRequest("Idempotency-Key is required")
        if not command.prompt.strip() or not command.thread_id.strip():
            raise InvalidRequest("prompt and thread_id are required")
        if not 1 <= command.max_attempts <= 8:
            raise InvalidRequest("max_attempts must be between 1 and 8")

        job, replayed = self.store.create_or_replay(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            payload=command.canonical_payload(),
            max_attempts=command.max_attempts,
        )
        return {
            "status_code": 202,
            "body": job.public(),
            "headers": {"Location": f"/v1/agent-jobs/{job.job_id}"},
            "replayed": replayed,
        }

    def get_job(self, job_id: str, *, auth: AuthContext) -> dict:
        return {"status_code": 200, "body": self.store.get(job_id, auth.tenant_id).public()}

    def cancel_job(self, job_id: str, *, auth: AuthContext) -> dict:
        job = self.store.request_cancel(job_id, auth.tenant_id)
        code = 202 if job.status == JobStatus.CANCEL_REQUESTED else 200
        return {"status_code": code, "body": job.public()}

    def live(self) -> dict:
        return {"status_code": 200, "body": {"status": "alive"}}

    def ready(self) -> dict:
        checks = {"database": bool(self.database_probe()), "broker": bool(self.broker_probe())}
        ready = all(checks.values())
        return {
            "status_code": 200 if ready else 503,
            "body": {"status": "ready" if ready else "not_ready", "checks": checks},
        }

    def event_stream(self, job_id: str, *, auth: AuthContext, after_cursor: int = 0) -> Iterator[str]:
        for event in self.store.events_after(job_id, auth.tenant_id, after_cursor):
            yield format_sse(event)

    @staticmethod
    def _ping_redis() -> bool:
        try:
            from redis import Redis

            from app.config import get_settings

            return bool(Redis.from_url(get_settings().redis_url).ping())
        except Exception:
            return False


def format_sse(event: JobEvent) -> str:
    body = json.dumps(
        {
            "job_id": event.job_id,
            "status": event.status.value,
            "detail": event.detail,
            "created_at": event.created_at,
        },
        sort_keys=True,
    )
    return f"id: {event.cursor}\nevent: {event.event_type}\ndata: {body}\n\n"
