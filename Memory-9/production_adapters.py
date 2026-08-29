"""Optional production adapter sketches.

The classroom gate runs against SQLite so the session works without Docker or
network access. These adapters keep the same boundary for Redis/PostgreSQL.
They intentionally fail with a clear message when optional clients are absent.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from memory_contracts import MemoryScope, ThreadState, ThreadTurn


class RedisThreadStateStore:
    def __init__(self, redis_url: str, *, ttl_seconds: int = 86400) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Install redis>=5 to use RedisThreadStateStore") from exc
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _key(thread_id: str, scope: MemoryScope) -> str:
        return ":".join(("agent", "thread", scope.tenant_id, scope.user_id, scope.agent_id, scope.purpose, thread_id))

    def load(self, thread_id: str, scope: MemoryScope) -> ThreadState | None:
        raw = self.client.get(self._key(thread_id, scope))
        if not raw:
            return None
        value = json.loads(raw)
        value["scope"] = MemoryScope(**value["scope"])
        value["recent_turns"] = tuple(ThreadTurn(**turn) for turn in value["recent_turns"])
        return ThreadState(**value)

    def save(self, state: ThreadState) -> ThreadState:
        next_state = ThreadState(**{**asdict(state), "scope": state.scope, "recent_turns": state.recent_turns, "version": state.version + 1})
        self.client.set(self._key(state.thread_id, state.scope), json.dumps(asdict(next_state)), ex=self.ttl_seconds)
        return next_state


class PostgresMemoryRepository:
    """Production port marker.

    Use `infra/postgres_schema.sql` and implement the same methods as
    `SQLiteMemoryRepository`. The critical invariant is that scope predicates
    are part of the SQL/vector query, never applied after retrieval.
    """

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install psycopg[binary,pool]>=3.2 to use PostgreSQL") from exc
        self.connection = psycopg.connect(dsn)

