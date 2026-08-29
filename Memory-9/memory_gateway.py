from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from embeddings import cosine, embed, estimate_tokens
from memory_contracts import (
    DeletionReceipt,
    MemoryCandidate,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    RecallBundle,
    RecallItem,
    WriteDecision,
    WriteOutcome,
)
from stores import SQLiteMemoryRepository


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MemoryGateway:
    """The only allowed boundary for durable memory reads, writes, and deletion."""

    ALLOWED_DURABLE_KINDS = {
        MemoryKind.SEMANTIC,
        MemoryKind.EPISODIC,
        MemoryKind.PROCEDURAL,
        MemoryKind.ENTITY,
        MemoryKind.ORGANIZATIONAL,
    }
    PROHIBITED_TERMS = (
        "password", "api key", "cvv", "card number", "private key", "access token"
    )
    SPECIAL_TERMS = ("diagnosis", "medical condition", "religion", "union membership")
    PERSONAL_TERMS = ("email", "phone", "address", "prefers", "preference", "name")
    MUTABLE_SYSTEM_KEYS = {"account_plan", "refund_status", "order_status", "credit_balance"}
    DEFAULT_TTLS = {
        MemoryKind.EPISODIC: 30 * 24 * 60 * 60,
        MemoryKind.SEMANTIC: 365 * 24 * 60 * 60,
        MemoryKind.ENTITY: 24 * 60 * 60,
        MemoryKind.ORGANIZATIONAL: 7 * 24 * 60 * 60,
        MemoryKind.PROCEDURAL: None,
    }

    def __init__(self, repository: SQLiteMemoryRepository, *, clock: Clock = utc_now) -> None:
        self.repository = repository
        self.clock = clock

    def _reject(self, candidate: MemoryCandidate, reason: str) -> WriteOutcome:
        now = iso(self.clock())
        self.repository.audit(now, "write_rejected", candidate.scope, reason)
        return WriteOutcome(WriteDecision.REJECTED, reason)

    def _sensitivity(self, candidate: MemoryCandidate) -> str:
        text = f"{candidate.key} {candidate.value}".lower()
        if any(term in text for term in self.PROHIBITED_TERMS):
            return "regulated"
        if any(term in text for term in self.SPECIAL_TERMS):
            return "special"
        if any(term in text for term in self.PERSONAL_TERMS):
            return "personal"
        return "internal"

    def remember(self, candidate: MemoryCandidate) -> WriteOutcome:
        # UNSAFE BASELINE. TODO 2: replace this direct write with validation,
        # classification, authorization, provenance and lifecycle policy.
        # Solution:
        for field_name in ("tenant_id", "user_id", "agent_id", "purpose"):
            if not getattr(candidate.scope, field_name).strip():
                return self._reject(candidate, f"missing_scope:{field_name}")
        if candidate.kind not in self.ALLOWED_DURABLE_KINDS:
            return self._reject(candidate, "wrong_store_for_ephemeral_memory")
        if not candidate.subject.strip() or not candidate.key.strip() or not candidate.value.strip():
            return self._reject(candidate, "invalid_empty_field")
        if not candidate.provenance.source_id or not candidate.provenance.evidence_excerpt:
            return self._reject(candidate, "missing_provenance")
        if not 0.0 <= candidate.confidence <= 1.0:
            return self._reject(candidate, "invalid_confidence")
        sensitivity = self._sensitivity(candidate)
        if sensitivity in {"regulated", "special"}:
            return self._reject(candidate, f"sensitivity_not_allowed:{sensitivity}")
        if candidate.provenance.source_kind == "model_inference" and not candidate.provenance.verified:
            return self._reject(candidate, "unverified_model_inference")
        if candidate.kind == MemoryKind.PROCEDURAL and candidate.scope.agent_id != "memory-admin":
            return self._reject(candidate, "procedural_write_requires_review")

        ttl_seconds = candidate.ttl_seconds
        if ttl_seconds is None:
            ttl_seconds = self.DEFAULT_TTLS[candidate.kind]
        if ttl_seconds is not None and ttl_seconds <= 0:
            return self._reject(candidate, "invalid_ttl")
        if candidate.key in self.MUTABLE_SYSTEM_KEYS:
            if candidate.provenance.source_kind != "system_of_record" or not candidate.provenance.verified:
                return self._reject(candidate, "mutable_fact_requires_system_of_record")
            ttl_seconds = min(ttl_seconds or 300, 300)

        existing = self.repository.find_current(
            candidate.scope, candidate.subject.strip(), candidate.key.strip()
        )
        normalized_value = re.sub(r"\s+", " ", candidate.value.strip()).casefold()
        if existing and re.sub(r"\s+", " ", existing.value.strip()).casefold() == normalized_value:
            self.repository.audit(iso(self.clock()), "write_deduplicated", candidate.scope, existing.memory_id)
            return WriteOutcome(WriteDecision.DEDUPLICATED, "equivalent_current_memory", existing)
        if existing and parse_iso(candidate.provenance.observed_at) < parse_iso(existing.provenance.observed_at):
            return self._reject(candidate, "stale_conflict")

        now = self.clock()
        expires_at = iso(now + timedelta(seconds=ttl_seconds)) if ttl_seconds else None

        # existing code below:

        now = self.clock()
        record = MemoryRecord(
            memory_id=uuid.uuid4().hex,
            kind=candidate.kind,
            subject=candidate.subject,
            key=candidate.key,
            value=candidate.value,
            scope=candidate.scope,
            provenance=candidate.provenance,
            confidence=candidate.confidence,
            sensitivity="unclassified",
            valid_from=candidate.provenance.observed_at,
            valid_to=None,
            expires_at=None,
            supersedes_id=None,
            status=MemoryStatus.ACTIVE,
            embedding=embed(f"{candidate.subject} {candidate.key} {candidate.value}"),
            created_at=iso(now),
        )

        # TODO 3: deduplicate equivalent facts and supersede newer conflicts atomically.
        # self.repository.replace_current(record, None)
        # self.repository.audit(iso(now), "unsafe_direct_write", candidate.scope, record.memory_id)
        # return WriteOutcome(WriteDecision.STORED, "unsafe_direct_write", record)
        self.repository.replace_current(record, existing.memory_id if existing else None)
        action = "write_superseded" if existing else "write_stored"
        self.repository.audit(iso(now), action, candidate.scope, record.memory_id)
        return WriteOutcome(WriteDecision.STORED, action, record)



    def recall(
        self,
        query: str,
        *,
        scope: MemoryScope,
        kinds: tuple[MemoryKind, ...] = (MemoryKind.SEMANTIC, MemoryKind.EPISODIC),
        token_budget: int = 120,
        top_k: int = 5,
    ) -> RecallBundle:
        # UNSAFE BASELINE. TODO 4: push scope and expiry filters into the store
        # before similarity ranking, then enforce top-k and token budget.
        candidates = [record for record in self.repository.all_records() if record.status == MemoryStatus.ACTIVE]
        query_vector = embed(query)
        items = tuple(
            RecallItem(
                record,
                max(0.0, cosine(query_vector, record.embedding)),
                estimate_tokens(f"{record.key}: {record.value}"),
                "unsafe_global_similarity",
            )
            for record in sorted(
                candidates,
                key=lambda item: cosine(query_vector, item.embedding),
                reverse=True,
            )
        )
        used = sum(item.token_cost for item in items)
        self.repository.audit(iso(self.clock()), "unsafe_read", scope, f"considered={len(candidates)}")
        return RecallBundle(items, used, len(candidates))

        # Instructor implementation begins below. Remove the unsafe return while solving.
        if token_budget <= 0:
            return RecallBundle((), 0, 0)
        now = self.clock()
        # Scope is pushed into SQL before any similarity work.
        candidates = [
            record for record in self.repository.scoped_candidates(scope, kinds)
            if not record.expires_at or parse_iso(record.expires_at) > now
        ]
        query_vector = embed(query)
        scored: list[RecallItem] = []
        for record in candidates:
            similarity = max(0.0, cosine(query_vector, record.embedding))
            age_days = max(0.0, (now - parse_iso(record.provenance.observed_at)).total_seconds() / 86400)
            recency = 1.0 / (1.0 + age_days / 30.0)
            score = 0.70 * similarity + 0.20 * record.confidence + 0.10 * recency
            cost = estimate_tokens(f"{record.key}: {record.value}")
            scored.append(RecallItem(record, score, cost, "semantic+confidence+recency"))
        scored.sort(key=lambda item: item.score, reverse=True)

        selected: list[RecallItem] = []
        used = 0
        for item in scored:
            if len(selected) >= top_k:
                break
            if used + item.token_cost > token_budget:
                continue
            selected.append(item)
            used += item.token_cost
        self.repository.audit(
            iso(now), "read", scope,
            f"query_hash={hashlib.sha256(query.encode()).hexdigest()[:10]} considered={len(candidates)} selected={len(selected)}",
        )
        return RecallBundle(tuple(selected), used, len(candidates))

    def forget(self, subject: str, *, scope: MemoryScope) -> DeletionReceipt:
        # TODO 5: delete content and derived embeddings, then retain only a tombstone.
        now = iso(self.clock())
        return DeletionReceipt(
            tombstone_id=uuid.uuid4().hex,
            subject_hash="not-deleted",
            deleted_count=0,
            deleted_at=now,
            scope=scope,
        )

        # Instructor implementation begins below. Remove the unsafe return while solving.
        now = iso(self.clock())
        deleted_ids = self.repository.delete_subject(scope, subject, now)
        subject_hash = hashlib.sha256(
            f"{scope.tenant_id}:{scope.user_id}:{subject}".encode("utf-8")
        ).hexdigest()[:16]
        receipt = DeletionReceipt(
            tombstone_id=uuid.uuid4().hex,
            subject_hash=subject_hash,
            deleted_count=len(deleted_ids),
            deleted_at=now,
            scope=scope,
        )
        self.repository.audit(now, "delete", scope, f"tombstone={receipt.tombstone_id} count={len(deleted_ids)}")
        return receipt
