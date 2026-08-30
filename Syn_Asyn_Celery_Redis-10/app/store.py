from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.contracts import ALLOWED_TRANSITIONS, TERMINAL, JobEvent, JobRecord, JobStatus
from app.db import db_connection
from app.errors import IdempotencyConflict, InvalidTransition, JobNotFound


def utc_now() -> datetime:
    return datetime.now(UTC)


def request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _job(row: dict[str, Any]) -> JobRecord:
    return JobRecord(
        job_id=str(row["job_id"]),
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        idempotency_key=row["idempotency_key"],
        request_hash=row["request_hash"],
        payload=row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
        status=JobStatus(row["status"]),
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        checkpoint_index=row["checkpoint_index"],
        cancel_requested=bool(row["cancel_requested"]),
        next_retry_delay=row["next_retry_delay"],
        result=row["result"] if row["result"] is None or isinstance(row["result"], dict) else json.loads(row["result"]),
        error=row["error"],
        version=row["version"],
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
    )


class PostgresJobStore:
    """Durable job truth. Redis/Celery only deliver work."""

    def create_or_replay(
        self,
        *,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        max_attempts: int,
    ) -> tuple[JobRecord, bool]:
        fingerprint = request_fingerprint(payload)
        expires_at = utc_now() + timedelta(hours=get_settings().idempotency_ttl_hours)
        with db_connection() as conn:
            with conn.transaction():
                prior = conn.execute(
                    """
                    SELECT request_hash, job_id FROM idempotency_keys
                    WHERE tenant_id=%s AND idempotency_key=%s
                    """,
                    (tenant_id, idempotency_key),
                ).fetchone()
                if prior:
                    if prior["request_hash"] != fingerprint:
                        raise IdempotencyConflict("idempotency key was already used with a different payload")
                    return self.get(str(prior["job_id"]), tenant_id), True

                job_id = str(uuid.uuid4())
                now = utc_now()
                # Accept + queue + outbox in one transaction so delivery cannot race ahead of durable queued state.
                conn.execute(
                    """
                    INSERT INTO agent_jobs (
                      job_id, tenant_id, user_id, idempotency_key, request_hash, payload,
                      status, max_attempts, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                    """,
                    (
                        job_id,
                        tenant_id,
                        user_id,
                        idempotency_key,
                        fingerprint,
                        json.dumps(payload),
                        JobStatus.QUEUED.value,
                        max_attempts,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO idempotency_keys
                    (tenant_id, idempotency_key, request_hash, job_id, created_at, expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (tenant_id, idempotency_key, fingerprint, job_id, now, expires_at),
                )
                self._append_event(conn, job_id, tenant_id, "job.accepted", JobStatus.ACCEPTED, {})
                self._append_event(conn, job_id, tenant_id, "job.queued", JobStatus.QUEUED, {})
                conn.execute(
                    """
                    INSERT INTO job_outbox (job_id, topic, payload)
                    VALUES (%s, 'agent.run', %s::jsonb)
                    """,
                    (job_id, json.dumps({"job_id": job_id})),
                )
            return self.get(job_id, tenant_id), False

    def get(self, job_id: str, tenant_id: str | None = None) -> JobRecord:
        with db_connection() as conn:
            if tenant_id is None:
                row = conn.execute("SELECT * FROM agent_jobs WHERE job_id=%s", (job_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM agent_jobs WHERE job_id=%s AND tenant_id=%s",
                    (job_id, tenant_id),
                ).fetchone()
            if not row:
                raise JobNotFound("job not found")
            return _job(row)

    def transition(
        self,
        job_id: str,
        next_status: JobStatus,
        *,
        event_type: str | None = None,
        detail: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        next_retry_delay: float | None = None,
        tenant_id: str | None = None,
    ) -> JobRecord:
        with db_connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM agent_jobs WHERE job_id=%s FOR UPDATE",
                    (job_id,),
                ).fetchone()
                if not row:
                    raise JobNotFound("job not found")
                if tenant_id is not None and row["tenant_id"] != tenant_id:
                    raise JobNotFound("job not found")
                current = JobStatus(row["status"])
                if current in TERMINAL or next_status not in ALLOWED_TRANSITIONS.get(current, set()):
                    raise InvalidTransition(f"{current.value} -> {next_status.value} is not allowed")
                now = utc_now()
                cancel_flag = next_status == JobStatus.CANCEL_REQUESTED
                updated = conn.execute(
                    """
                    UPDATE agent_jobs SET
                      status=%s,
                      cancel_requested=CASE WHEN %s THEN true ELSE cancel_requested END,
                      result=COALESCE(%s::jsonb, result),
                      error=COALESCE(%s, error),
                      next_retry_delay=%s,
                      version=version+1,
                      updated_at=%s
                    WHERE job_id=%s AND version=%s
                    RETURNING *
                    """,
                    (
                        next_status.value,
                        cancel_flag,
                        json.dumps(result) if result is not None else None,
                        error,
                        next_retry_delay,
                        now,
                        job_id,
                        row["version"],
                    ),
                ).fetchone()
                if not updated:
                    raise InvalidTransition("optimistic version conflict")
                self._append_event(
                    conn,
                    job_id,
                    row["tenant_id"],
                    event_type or f"job.{next_status.value}",
                    next_status,
                    detail or {},
                )
                return _job(updated)

    def begin_attempt(self, job_id: str) -> JobRecord:
        """Atomically move queued work to running and count the attempt."""
        with db_connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM agent_jobs WHERE job_id=%s FOR UPDATE",
                    (job_id,),
                ).fetchone()
                if not row:
                    raise JobNotFound("job not found")
                current = JobStatus(row["status"])
                if current != JobStatus.QUEUED:
                    raise InvalidTransition(f"{current.value} -> running is not allowed")
                updated = conn.execute(
                    """
                    UPDATE agent_jobs
                    SET status=%s, attempts=attempts+1, version=version+1, updated_at=%s
                    WHERE job_id=%s AND version=%s
                    RETURNING *
                    """,
                    (JobStatus.RUNNING.value, utc_now(), job_id, row["version"]),
                ).fetchone()
                if not updated:
                    raise InvalidTransition("optimistic version conflict")
                self._append_event(
                    conn,
                    job_id,
                    row["tenant_id"],
                    "worker.started",
                    JobStatus.RUNNING,
                    {"attempt": int(row["attempts"]) + 1},
                )
                return _job(updated)

    def request_cancel(self, job_id: str, tenant_id: str) -> JobRecord:
        job = self.get(job_id, tenant_id)
        if job.status in TERMINAL or job.status == JobStatus.CANCEL_REQUESTED:
            return job
        try:
            return self.transition(
                job_id,
                JobStatus.CANCEL_REQUESTED,
                event_type="job.cancel_requested",
                tenant_id=tenant_id,
            )
        except InvalidTransition:
            # Worker may have advanced concurrently; return current scoped row.
            return self.get(job_id, tenant_id)

    def save_checkpoint(self, job_id: str, checkpoint_index: int, step: str) -> None:
        with db_connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE agent_jobs
                    SET checkpoint_index=%s, version=version+1, updated_at=%s
                    WHERE job_id=%s
                    RETURNING tenant_id, status
                    """,
                    (checkpoint_index, utc_now(), job_id),
                ).fetchone()
                self._append_event(
                    conn,
                    job_id,
                    row["tenant_id"],
                    "workflow.checkpoint",
                    JobStatus(row["status"]),
                    {"step": step, "checkpoint_index": checkpoint_index},
                )

    def record_side_effect_once(self, job_id: str, step_key: str, output: dict[str, Any]) -> bool:
        with db_connection() as conn:
            with conn.transaction():
                cur = conn.execute(
                    """
                    INSERT INTO workflow_side_effects (job_id, step_key, output)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (job_id, step_key) DO NOTHING
                    """,
                    (job_id, step_key, json.dumps(output)),
                )
                return cur.rowcount > 0

    def side_effect_count(self, job_id: str, step_key: str) -> int:
        with db_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM workflow_side_effects WHERE job_id=%s AND step_key=%s",
                (job_id, step_key),
            ).fetchone()
            return int(row["n"])

    def get_side_effect(self, job_id: str, step_key: str) -> dict[str, Any] | None:
        with db_connection() as conn:
            row = conn.execute(
                "SELECT output FROM workflow_side_effects WHERE job_id=%s AND step_key=%s",
                (job_id, step_key),
            ).fetchone()
            if not row:
                return None
            out = row["output"]
            return out if isinstance(out, dict) else json.loads(out)

    def events_after(self, job_id: str, tenant_id: str, cursor: int = 0) -> list[JobEvent]:
        self.get(job_id, tenant_id)
        with db_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_events
                WHERE job_id=%s AND tenant_id=%s AND cursor>%s
                ORDER BY cursor
                """,
                (job_id, tenant_id, cursor),
            ).fetchall()
            return [
                JobEvent(
                    cursor=row["cursor"],
                    job_id=str(row["job_id"]),
                    tenant_id=row["tenant_id"],
                    event_type=row["event_type"],
                    status=JobStatus(row["status"]),
                    detail=row["detail"] if isinstance(row["detail"], dict) else json.loads(row["detail"]),
                    created_at=row["created_at"].isoformat()
                    if hasattr(row["created_at"], "isoformat")
                    else str(row["created_at"]),
                )
                for row in rows
            ]

    def claim_unpublished_outbox(self, limit: int = 20) -> list[dict[str, Any]]:
        """Persist a claim so concurrent publishers cannot take the same row."""
        claim_token = str(uuid.uuid4())
        claim_timeout = get_settings().outbox_claim_timeout_seconds
        with db_connection() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    WITH candidates AS (
                      SELECT event_id
                      FROM job_outbox
                      WHERE published_at IS NULL
                        AND available_at <= now()
                        AND (
                          claimed_at IS NULL
                          OR claimed_at < now() - (%s * interval '1 second')
                        )
                      ORDER BY event_id
                      LIMIT %s
                      FOR UPDATE SKIP LOCKED
                    )
                    UPDATE job_outbox AS outbox
                    SET claimed_at=now(), claim_token=%s, publish_attempts=publish_attempts+1
                    FROM candidates
                    WHERE outbox.event_id=candidates.event_id
                    RETURNING outbox.event_id, outbox.job_id, outbox.topic,
                              outbox.payload, outbox.claim_token, outbox.publish_attempts
                    """,
                    (claim_timeout, limit, claim_token),
                ).fetchall()
                return [
                    {
                        "event_id": row["event_id"],
                        "job_id": str(row["job_id"]),
                        "topic": row["topic"],
                        "payload": row["payload"]
                        if isinstance(row["payload"], dict)
                        else json.loads(row["payload"]),
                        "claim_token": str(row["claim_token"]),
                        "publish_attempts": int(row["publish_attempts"]),
                    }
                    for row in rows
                ]

    def mark_outbox_published(self, event_id: int, claim_token: str) -> None:
        with db_connection() as conn:
            with conn.transaction():
                updated = conn.execute(
                    """
                    UPDATE job_outbox
                    SET published_at=%s, claimed_at=NULL, claim_token=NULL
                    WHERE event_id=%s AND claim_token=%s AND published_at IS NULL
                    """,
                    (utc_now(), event_id, claim_token),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("outbox claim was lost before publish confirmation")

    def release_outbox_claim(self, event_id: int, claim_token: str) -> None:
        with db_connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    UPDATE job_outbox
                    SET claimed_at=NULL, claim_token=NULL
                    WHERE event_id=%s AND claim_token=%s AND published_at IS NULL
                    """,
                    (event_id, claim_token),
                )

    def enqueue_retry_outbox(self, job_id: str, delay_seconds: float) -> None:
        with db_connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO job_outbox (job_id, topic, payload, available_at)
                    VALUES (%s, 'agent.run', %s::jsonb, now() + (%s * interval '1 second'))
                    """,
                    (job_id, json.dumps({"job_id": job_id}), delay_seconds),
                )

    @staticmethod
    def _append_event(conn, job_id: str, tenant_id: str, event_type: str, status: JobStatus, detail: dict) -> None:
        conn.execute(
            """
            INSERT INTO job_events (job_id, tenant_id, event_type, status, detail, created_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s)
            """,
            (job_id, tenant_id, event_type, status.value, json.dumps(detail), utc_now()),
        )
