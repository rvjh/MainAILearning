from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryStrategy:
    name: str
    scope: str
    use_when: str
    main_risk: str


STRATEGY_CATALOG = (
    MemoryStrategy("full buffer", "thread", "short, bounded conversations", "unbounded tokens"),
    MemoryStrategy("sliding window", "thread", "recent turns dominate", "loses older commitments"),
    MemoryStrategy("rolling summary", "thread", "long conversations", "summary drift"),
    MemoryStrategy("checkpoint", "run/thread", "pause, resume, recovery", "stale concurrent resume"),
    MemoryStrategy("semantic profile", "cross-thread", "small stable user profile", "conflicting fields"),
    MemoryStrategy("semantic collection", "cross-thread", "many independent facts", "duplication and bloat"),
    MemoryStrategy("episodic retrieval", "cross-thread", "reuse successful examples", "copying obsolete behavior"),
    MemoryStrategy("procedural memory", "agent/version", "versioned rules and playbooks", "self-modifying behavior"),
    MemoryStrategy("entity/graph memory", "domain", "precise relationships and multi-hop lookup", "identity errors"),
    MemoryStrategy("background consolidation", "cross-thread", "merge and compress off the hot path", "eventual consistency"),
    MemoryStrategy("TTL and forgetting", "all tiers", "bound risk, cost, and staleness", "premature loss"),
    MemoryStrategy("scope-first retrieval", "all durable tiers", "multi-user and multi-tenant systems", "recall loss if filters are wrong"),
)


def names() -> tuple[str, ...]:
    return tuple(strategy.name for strategy in STRATEGY_CATALOG)

