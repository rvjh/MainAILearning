from typing import Any


class JobStore:
    """In-memory job metadata registry. Redis remains the source of truth for job state."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def register(self, job_id: str, query: str) -> None:
        self._jobs[job_id] = {"query": query}

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)


job_store = JobStore()
