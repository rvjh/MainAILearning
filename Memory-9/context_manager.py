from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from embeddings import estimate_tokens, tokenize
from memory_contracts import (
    AssembledContext,
    ContextPart,
    MemoryKind,
    MemoryScope,
    ThreadState,
    ThreadTurn,
)
from memory_gateway import MemoryGateway
from stores import SQLiteThreadStateStore


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(text: str, limit: int) -> str:
    words = text.split()
    return " ".join(words[:limit])


class ContextManager:
    """Composes bounded context from checkpointed thread state and long-term recall."""

    def __init__(
        self,
        thread_store: SQLiteThreadStateStore,
        memory_gateway: MemoryGateway,
        *,
        recent_turn_limit: int = 6,
        summary_token_limit: int = 80,
        thread_ttl_seconds: int = 24 * 60 * 60,
        clock: Clock = utc_now,
    ) -> None:
        self.thread_store = thread_store
        self.memory_gateway = memory_gateway
        self.recent_turn_limit = recent_turn_limit
        self.summary_token_limit = summary_token_limit
        self.thread_ttl_seconds = thread_ttl_seconds
        self.clock = clock

    def append_turn(self, thread_id: str, scope: MemoryScope, role: str, content: str) -> ThreadState:
        now = self.clock()
        state = self.thread_store.load(thread_id, scope) or ThreadState(thread_id, scope)
        turns = list(state.recent_turns)
        turns.append(ThreadTurn(role=role, content=content, created_at=now.isoformat()))
        summary = state.summary
        # TODO 1: compact evicted turns into a bounded rolling summary.
        if len(turns) > self.recent_turn_limit:
            evicted = turns[:-self.recent_turn_limit]
            turns = turns[-self.recent_turn_limit:]
            additions = " ".join(f"{turn.role}: {turn.content}" for turn in evicted)
            summary = _truncate(f"{summary} {additions}".strip(), self.summary_token_limit) # Use llm to compact the summary
        next_state = ThreadState(
            thread_id=thread_id,
            scope=scope,
            summary=summary,
            recent_turns=tuple(turns),
            version=state.version,
            updated_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.thread_ttl_seconds)).isoformat(),
        )
        return self.thread_store.save(next_state)

    def build_context(
        self,
        query: str,
        *,
        thread_id: str,
        scope: MemoryScope,
        token_budget: int = 240,
    ) -> AssembledContext:
        if token_budget <= 0:
            return AssembledContext((), 0, token_budget, {"reason": "zero_budget"})
        state = self.thread_store.load(thread_id, scope)
        parts: list[ContextPart] = []
        used = 0

        if state and state.summary:
            summary_budget = max(1, token_budget // 4)
            text = _truncate(state.summary, summary_budget)
            cost = estimate_tokens(text)
            parts.append(ContextPart("thread_summary", text, cost))
            used += cost

        if state:
            recent_budget = max(1, token_budget * 2 // 5)
            chosen: list[ContextPart] = []
            recent_used = 0
            for turn in reversed(state.recent_turns):
                text = f"{turn.role}: {turn.content}"
                cost = estimate_tokens(text)
                if recent_used + cost > recent_budget:
                    continue
                chosen.append(ContextPart("recent_turn", text, cost))
                recent_used += cost
            parts.extend(reversed(chosen))
            used += recent_used

        remaining = max(0, token_budget - used)
        recalled = self.memory_gateway.recall(
            query,
            scope=scope,
            kinds=(MemoryKind.SEMANTIC, MemoryKind.EPISODIC),
            token_budget=remaining,
            top_k=5,
        )
        for item in recalled.items:
            text = f"{item.record.key}: {item.record.value}"
            parts.append(ContextPart("long_term_memory", text, item.token_cost, item.record.memory_id))
            used += item.token_cost

        return AssembledContext(
            parts=tuple(parts),
            token_count=used,
            token_budget=token_budget,
            diagnostics={
                "thread_version": state.version if state else None,
                "long_term_considered_after_scope": recalled.considered_after_scope,
                "long_term_selected": len(recalled.items),
            },
        )
