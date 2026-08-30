from __future__ import annotations

import time
import logging

from celery import Celery

from app.config import get_settings
settings = get_settings()
logger = logging.getLogger(__name__)

app = Celery(
    "agent_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


@app.task(
    bind=True,
    name="agent.run_job",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_agent_job(self, job_id: str) -> dict:
    # Lazy import so the outbox process never loads LangGraph / LangChain.
    from app.store import PostgresJobStore
    from app.worker import Worker

    job = Worker(PostgresJobStore()).process(job_id)
    return job.public()


@app.task(name="agent.publish_outbox")
def publish_outbox(limit: int = 50) -> dict:
    """Transactional outbox publisher: DB commit first, then Celery delivery."""
    from app.store import PostgresJobStore

    store = PostgresJobStore()
    claimed = store.claim_unpublished_outbox(limit=limit)
    published = 0
    for item in claimed:
        try:
            run_agent_job.delay(item["job_id"])
            store.mark_outbox_published(item["event_id"], item["claim_token"])
            published += 1
        except Exception:
            store.release_outbox_claim(item["event_id"], item["claim_token"])
            raise
    return {"claimed": len(claimed), "published": published}


def outbox_loop(poll_seconds: float | None = None) -> None:
    poll = poll_seconds if poll_seconds is not None else settings.outbox_poll_seconds
    while True:
        try:
            publish_outbox()
        except Exception:
            logger.exception("outbox publish cycle failed; released claims will be retried")
        time.sleep(poll)
