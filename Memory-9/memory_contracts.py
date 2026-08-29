from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryKind(str, Enum):
    WORKING = "working"
    CONVERSATIONAL = "conversational"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    ENTITY = "entity"
    PROCEDURAL = "procedural"
    ORGANIZATIONAL = "organizational"
    AUDIT = "audit"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class WriteDecision(str, Enum):
    STORED = "stored"
    DEDUPLICATED = "deduplicated"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MemoryScope:
    tenant_id: str
    user_id: str
    agent_id: str
    purpose: str

    def namespace(self, kind: MemoryKind) -> tuple[str, ...]:
        return (self.tenant_id, self.user_id, self.agent_id, self.purpose, kind.value)


@dataclass(frozen=True)
class Provenance:
    source_kind: str
    source_id: str
    actor_id: str
    observed_at: str
    evidence_excerpt: str
    verified: bool = False


@dataclass(frozen=True)
class MemoryCandidate:
    kind: MemoryKind
    subject: str
    key: str
    value: str
    scope: MemoryScope
    provenance: Provenance
    confidence: float = 1.0
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    kind: MemoryKind
    subject: str
    key: str
    value: str
    scope: MemoryScope
    provenance: Provenance
    confidence: float
    sensitivity: str
    valid_from: str
    valid_to: str | None
    expires_at: str | None
    supersedes_id: str | None
    status: MemoryStatus
    embedding: tuple[float, ...]
    created_at: str


@dataclass(frozen=True)
class WriteOutcome:
    decision: WriteDecision
    reason: str
    record: MemoryRecord | None = None


@dataclass(frozen=True)
class RecallItem:
    record: MemoryRecord
    score: float
    token_cost: int
    reason: str


@dataclass(frozen=True)
class RecallBundle:
    items: tuple[RecallItem, ...]
    token_count: int
    considered_after_scope: int


@dataclass(frozen=True)
class ThreadTurn:
    role: str
    content: str
    created_at: str


@dataclass(frozen=True)
class ThreadState:
    thread_id: str
    scope: MemoryScope
    summary: str = ""
    recent_turns: tuple[ThreadTurn, ...] = ()
    version: int = 0
    updated_at: str = ""
    expires_at: str | None = None


@dataclass(frozen=True)
class ContextPart:
    source: str
    text: str
    token_cost: int
    reference_id: str | None = None


@dataclass(frozen=True)
class AssembledContext:
    parts: tuple[ContextPart, ...]
    token_count: int
    token_budget: int
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeletionReceipt:
    tombstone_id: str
    subject_hash: str
    deleted_count: int
    deleted_at: str
    scope: MemoryScope

