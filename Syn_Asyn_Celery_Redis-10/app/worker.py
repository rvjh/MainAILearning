from __future__ import annotations

from dataclasses import dataclass

from app.agent_pipeline import AgentPipeline
from app.contracts import JobRecord, JobStatus
from app.errors import PermanentFailure, PolicyFailure, TransientFailure, WorkerLost
from app.store import PostgresJobStore


@dataclass(frozen=True)
class RetryPolicy:
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def delay(self, attempts: int) -> float:
        # Deterministic for demos; Celery also applies jitter on broker retries.
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** max(0, attempts - 1)))


class Worker:
    def __init__(
        self,
        store: PostgresJobStore | None = None,
        *,
        pipeline: AgentPipeline | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.store = store or PostgresJobStore()
        self.pipeline = pipeline or AgentPipeline()
        self.retry_policy = retry_policy or RetryPolicy()

    def process(self, job_id: str) -> JobRecord:
        job = self.store.get(job_id)
        if job.status == JobStatus.CANCEL_REQUESTED:
            return self.store.transition(job_id, JobStatus.CANCELLED, event_type="worker.cancelled")
        if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING}:
            return job

        # Move retrying → queued → running if needed.
        if job.status == JobStatus.RETRYING:
            self.store.transition(job_id, JobStatus.QUEUED, event_type="worker.requeued")
        job = self.store.begin_attempt(job_id)
        prior: dict = {}
        try:
            for index, step in enumerate(self.pipeline.steps[job.checkpoint_index :], start=job.checkpoint_index):
                job = self.store.get(job_id)
                if job.cancel_requested or job.status == JobStatus.CANCEL_REQUESTED:
                    return self.store.transition(job_id, JobStatus.CANCELLED, event_type="worker.cancelled")

                existing = self.store.get_side_effect(job_id, step)
                if existing is not None:
                    output = existing
                else:
                    output = self.pipeline.run_step(job, step, prior)
                    self.store.record_side_effect_once(job_id, step, output)
                prior[step] = output
                self.store.save_checkpoint(job_id, index + 1, step)

            final_answer = prior.get("persist", {}).get("answer") or prior.get("execute", {}).get("answer")
            return self.store.transition(
                job_id,
                JobStatus.SUCCEEDED,
                event_type="worker.succeeded",
                result={
                    "answer": final_answer,
                    "completed_steps": list(self.pipeline.steps),
                    "memory_write": prior.get("persist", {}).get("memory_write"),
                    "memory_rejected": prior.get("persist", {}).get("memory_rejected"),
                    "provider": prior.get("execute", {}).get("model"),
                },
            )
        except WorkerLost:
            raise
        except TransientFailure as exc:
            current = self.store.get(job_id)
            if current.attempts >= current.max_attempts:
                return self.store.transition(
                    job_id, JobStatus.DEAD_LETTERED, event_type="worker.dead_lettered", error=str(exc)
                )
            delay = self.retry_policy.delay(current.attempts)
            retrying = self.store.transition(
                job_id,
                JobStatus.RETRYING,
                event_type="worker.retry_scheduled",
                detail={"attempt": current.attempts, "delay_seconds": delay},
                error=str(exc),
                next_retry_delay=delay,
            )
            self.store.enqueue_retry_outbox(job_id, delay)
            return retrying
        except (PermanentFailure, PolicyFailure) as exc:
            return self.store.transition(job_id, JobStatus.FAILED, event_type="worker.failed", error=str(exc))
