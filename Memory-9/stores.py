from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from memory_contracts import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    Provenance,
    ThreadState,
    ThreadTurn,
)


class SQLiteMemoryRepository:
    """Offline teaching adapter. PostgreSQL uses the same repository contract."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                subject TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                value TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                evidence_excerpt TEXT NOT NULL,
                verified INTEGER NOT NULL,
                confidence REAL NOT NULL,
                sensitivity TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                expires_at TEXT,
                supersedes_id TEXT,
                status TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_scope
            ON memories(tenant_id, user_id, agent_id, purpose, kind, status);
            CREATE INDEX IF NOT EXISTS idx_memories_identity
            ON memories(tenant_id, user_id, subject, memory_key, status);
            CREATE TABLE IF NOT EXISTS memory_audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                action TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                detail TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            kind=MemoryKind(row["kind"]),
            subject=row["subject"],
            key=row["memory_key"],
            value=row["value"],
            scope=MemoryScope(row["tenant_id"], row["user_id"], row["agent_id"], row["purpose"]),
            provenance=Provenance(
                row["source_kind"], row["source_id"], row["actor_id"],
                row["observed_at"], row["evidence_excerpt"], bool(row["verified"]),
            ),
            confidence=row["confidence"],
            sensitivity=row["sensitivity"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            expires_at=row["expires_at"],
            supersedes_id=row["supersedes_id"],
            status=MemoryStatus(row["status"]),
            embedding=tuple(json.loads(row["embedding"])),
            created_at=row["created_at"],
        )

    def find_current(self, scope: MemoryScope, subject: str, key: str) -> MemoryRecord | None:
        row = self.connection.execute(
            """
            SELECT * FROM memories
            WHERE tenant_id=? AND user_id=? AND agent_id=? AND purpose=?
              AND subject=? AND memory_key=? AND status='active'
            ORDER BY created_at DESC LIMIT 1
            """,
            (*asdict(scope).values(), subject, key),
        ).fetchone()
        return self._record(row) if row else None

    def replace_current(self, record: MemoryRecord, previous_id: str | None) -> None:
        with self.connection:
            if previous_id:
                self.connection.execute(
                    "UPDATE memories SET status='superseded', valid_to=? WHERE memory_id=? AND status='active'",
                    (record.created_at, previous_id),
                )
            self.connection.execute(
                """
                INSERT INTO memories(
                    memory_id, kind, subject, memory_key, value,
                    tenant_id, user_id, agent_id, purpose,
                    source_kind, source_id, actor_id, observed_at,
                    evidence_excerpt, verified, confidence, sensitivity,
                    valid_from, valid_to, expires_at, supersedes_id,
                    status, embedding, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.memory_id, record.kind.value, record.subject, record.key, record.value,
                    record.scope.tenant_id, record.scope.user_id, record.scope.agent_id, record.scope.purpose,
                    record.provenance.source_kind, record.provenance.source_id,
                    record.provenance.actor_id, record.provenance.observed_at,
                    record.provenance.evidence_excerpt, int(record.provenance.verified),
                    record.confidence, record.sensitivity, record.valid_from, record.valid_to,
                    record.expires_at, record.supersedes_id, record.status.value,
                    json.dumps(record.embedding), record.created_at,
                ),
            )

    def scoped_candidates(self, scope: MemoryScope, kinds: tuple[MemoryKind, ...]) -> list[MemoryRecord]:
        placeholders = ",".join("?" for _ in kinds)
        rows = self.connection.execute(
            f"""
            SELECT * FROM memories
            WHERE tenant_id=? AND user_id=? AND agent_id=? AND purpose=?
              AND status='active' AND kind IN ({placeholders})
            """,
            (*asdict(scope).values(), *(kind.value for kind in kinds)),
        ).fetchall()
        return [self._record(row) for row in rows]

    def delete_subject(self, scope: MemoryScope, subject: str, deleted_at: str) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT memory_id FROM memories
            WHERE tenant_id=? AND user_id=? AND agent_id=? AND purpose=?
              AND subject=? AND status='active'
            """,
            (*asdict(scope).values(), subject),
        ).fetchall()
        ids = [row["memory_id"] for row in rows]
        with self.connection:
            self.connection.execute(
                """
                UPDATE memories
                SET value='[DELETED]', embedding='[]', status='deleted', valid_to=?
                WHERE tenant_id=? AND user_id=? AND agent_id=? AND purpose=?
                  AND subject=? AND status='active'
                """,
                (deleted_at, *asdict(scope).values(), subject),
            )
        return ids

    def all_records(self) -> list[MemoryRecord]:
        return [self._record(row) for row in self.connection.execute("SELECT * FROM memories")]

    def audit(self, occurred_at: str, action: str, scope: MemoryScope, detail: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO memory_audit(
                    occurred_at, action, tenant_id, user_id, agent_id, purpose, detail
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (occurred_at, action, scope.tenant_id, scope.user_id, scope.agent_id, scope.purpose, detail),
            )

    def audit_events(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM memory_audit ORDER BY event_id")]


class SQLiteThreadStateStore:
    """Persistent thread/checkpoint adapter with strict namespace checks."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_states (
                thread_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                summary TEXT NOT NULL,
                recent_turns TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                PRIMARY KEY(thread_id, tenant_id, user_id, agent_id, purpose)
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def load(self, thread_id: str, scope: MemoryScope) -> ThreadState | None:
        row = self.connection.execute(
            """
            SELECT * FROM thread_states
            WHERE thread_id=? AND tenant_id=? AND user_id=? AND agent_id=? AND purpose=?
            """,
            (thread_id, *asdict(scope).values()),
        ).fetchone()
        if not row:
            return None
        turns = tuple(ThreadTurn(**turn) for turn in json.loads(row["recent_turns"]))
        return ThreadState(
            thread_id=row["thread_id"], scope=scope, summary=row["summary"],
            recent_turns=turns, version=row["version"], updated_at=row["updated_at"],
            expires_at=row["expires_at"],
        )

    def save(self, state: ThreadState) -> ThreadState:
        next_version = state.version + 1
        turns = json.dumps([asdict(turn) for turn in state.recent_turns])
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO thread_states VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(thread_id, tenant_id, user_id, agent_id, purpose)
                DO UPDATE SET summary=excluded.summary, recent_turns=excluded.recent_turns,
                              version=excluded.version, updated_at=excluded.updated_at,
                              expires_at=excluded.expires_at
                """,
                (
                    state.thread_id, state.scope.tenant_id, state.scope.user_id,
                    state.scope.agent_id, state.scope.purpose, state.summary, turns,
                    next_version, state.updated_at, state.expires_at,
                ),
            )
        return ThreadState(
            thread_id=state.thread_id, scope=state.scope, summary=state.summary,
            recent_turns=state.recent_turns, version=next_version,
            updated_at=state.updated_at, expires_at=state.expires_at,
        )
