from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from context_manager import ContextManager
from memory_contracts import MemoryCandidate, MemoryKind, MemoryScope, Provenance, WriteDecision
from memory_gateway import MemoryGateway
from memory_strategies import names
from stores import SQLiteMemoryRepository, SQLiteThreadStateStore


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 29, 4, 30, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.db = Path(self.temp.name) / "memory.sqlite3"
        self.clock = MutableClock()
        self.scope = MemoryScope("acme", "cust-1", "support-agent", "support")
        self.other = MemoryScope("globex", "cust-2", "support-agent", "support")
        self.repo = SQLiteMemoryRepository(self.db)
        self.threads = SQLiteThreadStateStore(self.db)
        self.gateway = MemoryGateway(self.repo, clock=self.clock)
        self.context = ContextManager(
            self.threads, self.gateway, recent_turn_limit=3,
            summary_token_limit=20, clock=self.clock,
        )

    def tearDown(self) -> None:
        self.repo.close()
        self.threads.close()
        self.temp.cleanup()

    def candidate(
        self,
        value: str,
        *,
        scope: MemoryScope | None = None,
        key: str = "contact_preference",
        kind: MemoryKind = MemoryKind.SEMANTIC,
        observed_at: str | None = None,
        source_kind: str = "user_asserted",
        verified: bool = True,
        ttl_seconds: int | None = None,
    ) -> MemoryCandidate:
        return MemoryCandidate(
            kind=kind,
            subject=(scope or self.scope).user_id,
            key=key,
            value=value,
            scope=scope or self.scope,
            provenance=Provenance(
                source_kind, "turn-1", "cust-1",
                observed_at or self.clock().isoformat(),
                f"evidence:{value}", verified,
            ),
            confidence=0.95,
            ttl_seconds=ttl_seconds,
        )

    def test_strategy_catalog_covers_common_patterns(self) -> None:
        catalog = set(names())
        for expected in {
            "full buffer", "sliding window", "rolling summary", "checkpoint",
            "semantic profile", "semantic collection", "episodic retrieval",
            "procedural memory", "background consolidation", "TTL and forgetting",
        }:
            self.assertIn(expected, catalog)

    def test_thread_state_compacts_to_summary_and_window(self) -> None:
        for index in range(5):
            state = self.context.append_turn("t-1", self.scope, "user", f"turn {index}")
        self.assertEqual(3, len(state.recent_turns))
        self.assertIn("turn 0", state.summary)
        self.assertLessEqual(len(state.summary.split()), 20)

    def test_thread_state_survives_restart(self) -> None:
        saved = self.context.append_turn("t-1", self.scope, "user", "hello")
        self.threads.close()
        reopened = SQLiteThreadStateStore(self.db)
        try:
            restored = reopened.load("t-1", self.scope)
            self.assertEqual(saved.version, restored.version)
            self.assertEqual("hello", restored.recent_turns[0].content)
        finally:
            reopened.close()
        self.threads = SQLiteThreadStateStore(self.db)

    def test_unverified_model_inference_is_rejected(self) -> None:
        outcome = self.gateway.remember(
            self.candidate("email", source_kind="model_inference", verified=False)
        )
        self.assertEqual(WriteDecision.REJECTED, outcome.decision)
        self.assertEqual("unverified_model_inference", outcome.reason)

    def test_regulated_secret_is_rejected(self) -> None:
        outcome = self.gateway.remember(self.candidate("card number 4111 and cvv 999"))
        self.assertEqual(WriteDecision.REJECTED, outcome.decision)

    def test_exact_duplicate_is_deduplicated(self) -> None:
        first = self.gateway.remember(self.candidate("Email"))
        second = self.gateway.remember(self.candidate(" email "))
        self.assertEqual(WriteDecision.STORED, first.decision)
        self.assertEqual(WriteDecision.DEDUPLICATED, second.decision)
        self.assertEqual(first.record.memory_id, second.record.memory_id)

    def test_newer_conflict_supersedes_without_overwrite(self) -> None:
        first = self.gateway.remember(self.candidate("email"))
        self.clock.value += timedelta(minutes=1)
        second = self.gateway.remember(self.candidate("SMS"))
        records = self.repo.all_records()
        self.assertEqual(first.record.memory_id, second.record.supersedes_id)
        self.assertEqual({"superseded", "active"}, {record.status.value for record in records})

    def test_older_conflict_is_rejected(self) -> None:
        self.gateway.remember(self.candidate("email"))
        older = (self.clock() - timedelta(days=1)).isoformat()
        outcome = self.gateway.remember(self.candidate("SMS", observed_at=older))
        self.assertEqual("stale_conflict", outcome.reason)

    def test_mutable_business_fact_requires_verified_system_of_record(self) -> None:
        rejected = self.gateway.remember(self.candidate("gold", key="account_plan"))
        allowed = self.gateway.remember(
            self.candidate("gold", key="account_plan", source_kind="system_of_record", verified=True)
        )
        self.assertEqual(WriteDecision.REJECTED, rejected.decision)
        self.assertEqual(WriteDecision.STORED, allowed.decision)
        expiry = datetime.fromisoformat(allowed.record.expires_at)
        self.assertLessEqual((expiry - self.clock()).total_seconds(), 300)

    def test_scope_is_applied_before_ranking(self) -> None:
        self.gateway.remember(self.candidate("email"))
        self.gateway.remember(self.candidate("phone", scope=self.other))
        recalled = self.gateway.recall("phone contact", scope=self.scope)
        self.assertEqual(1, recalled.considered_after_scope)
        self.assertTrue(all(item.record.scope == self.scope for item in recalled.items))

    def test_expired_memory_is_not_recalled(self) -> None:
        self.gateway.remember(self.candidate("email", ttl_seconds=5))
        self.clock.value += timedelta(seconds=6)
        recalled = self.gateway.recall("email", scope=self.scope)
        self.assertEqual(0, recalled.considered_after_scope)

    def test_context_respects_total_token_budget(self) -> None:
        for index in range(5):
            self.context.append_turn("t-1", self.scope, "user", f"conversation turn number {index}")
        self.gateway.remember(self.candidate("email for all account communication"))
        context = self.context.build_context("contact", thread_id="t-1", scope=self.scope, token_budget=20)
        self.assertLessEqual(context.token_count, 20)

    def test_forget_removes_content_and_embedding_but_keeps_tombstone_audit(self) -> None:
        self.gateway.remember(self.candidate("email"))
        receipt = self.gateway.forget(self.scope.user_id, scope=self.scope)
        records = self.repo.all_records()
        self.assertEqual(1, receipt.deleted_count)
        self.assertEqual("[DELETED]", records[0].value)
        self.assertEqual((), records[0].embedding)
        self.assertEqual(0, len(self.gateway.recall("email", scope=self.scope).items))
        self.assertTrue(any(event["action"] == "delete" for event in self.repo.audit_events()))

    def test_reads_and_denials_are_audited(self) -> None:
        self.gateway.remember(self.candidate("api key secret"))
        self.gateway.recall("contact", scope=self.scope)
        actions = [event["action"] for event in self.repo.audit_events()]
        self.assertIn("write_rejected", actions)
        self.assertIn("read", actions)


if __name__ == "__main__":
    unittest.main()

