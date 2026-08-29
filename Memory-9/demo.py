from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from context_manager import ContextManager
from memory_contracts import MemoryCandidate, MemoryKind, MemoryScope, Provenance
from memory_gateway import MemoryGateway
from stores import SQLiteMemoryRepository, SQLiteThreadStateStore


NOW = "2026-08-29T04:30:00+00:00"
ACME = MemoryScope("acme", "cust_8842", "support-agent", "customer_support")
GLOBEX = MemoryScope("globex", "cust_9001", "support-agent", "customer_support")


def candidate(scope: MemoryScope, value: str, *, source_kind: str = "user_asserted", verified: bool = True) -> MemoryCandidate:
    return MemoryCandidate(
        kind=MemoryKind.SEMANTIC,
        subject=scope.user_id,
        key="contact_preference",
        value=value,
        scope=scope,
        provenance=Provenance(source_kind, "turn-17", scope.user_id, NOW, f"User said: {value}", verified),
        confidence=0.98,
    )


with TemporaryDirectory() as directory:
    db = Path(directory) / "memory.sqlite3"
    repo = SQLiteMemoryRepository(db)
    thread_store = SQLiteThreadStateStore(db)
    gateway = MemoryGateway(repo)
    context = ContextManager(thread_store, gateway, recent_turn_limit=3)

    print("\n1. SHORT-TERM MEMORY: sliding window + rolling summary")
    for role, text in [
        ("user", "I need help with order A89268"),
        ("assistant", "I found the order."),
        ("user", "The box arrived damaged."),
        ("assistant", "I can help with the refund."),
        ("user", "Please contact me by email."),
    ]:
        state = context.append_turn("thread-42", ACME, role, text)
    print(" summary:", state.summary)
    print(" recent turns:", len(state.recent_turns), "version:", state.version)

    print("\n2. GOVERNED LONG-TERM WRITE")
    print(" stored:", gateway.remember(candidate(ACME, "email")).decision.value)
    print(" deduped:", gateway.remember(candidate(ACME, " email ")).decision.value)
    print(" rejected inference:", gateway.remember(candidate(ACME, "phone", source_kind="model_inference", verified=False)).reason)
    print(" superseded:", gateway.remember(candidate(ACME, "SMS")).record.supersedes_id is not None)
    gateway.remember(candidate(GLOBEX, "phone"))

    print("\n3. SCOPE-FIRST RECALL + CONTEXT BUDGET")
    bundle = context.build_context(
        "How should I contact this customer?", thread_id="thread-42", scope=ACME, token_budget=45
    )
    for part in bundle.parts:
        print(f" {part.source:18} {part.text}")
    print(" tokens:", bundle.token_count, "/", bundle.token_budget)
    print(" candidates after scope:", bundle.diagnostics["long_term_considered_after_scope"])

    print("\n4. PROCESS RESTART")
    repo.close()
    thread_store.close()
    reopened_threads = SQLiteThreadStateStore(db)
    restored = reopened_threads.load("thread-42", ACME)
    print(" restored version:", restored.version, "recent:", len(restored.recent_turns))

    print("\n5. FORGETTING + TOMBSTONE")
    reopened_repo = SQLiteMemoryRepository(db)
    reopened_gateway = MemoryGateway(reopened_repo)
    receipt = reopened_gateway.forget(ACME.user_id, scope=ACME)
    print(" deleted:", receipt.deleted_count, "subject hash:", receipt.subject_hash)
    print(" recall after delete:", len(reopened_gateway.recall("contact", scope=ACME).items))

