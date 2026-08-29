from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from context_manager import ContextManager
from memory_contracts import MemoryCandidate, MemoryScope, WriteOutcome
from memory_gateway import MemoryGateway


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citation_ids: tuple[str, ...]
    abstained: bool = False


RagAnswerer = Callable[[str, str, str], GroundedAnswer]


class MemoryAwareGroundedAgent:
    """Connects the existing grounded RAG answerer to bounded memory context."""

    def __init__(
        self,
        context_manager: ContextManager,
        memory_gateway: MemoryGateway,
        rag_answerer: RagAnswerer,
    ) -> None:
        self.context_manager = context_manager
        self.memory_gateway = memory_gateway
        self.rag_answerer = rag_answerer

    def handle(self, query: str, *, thread_id: str, scope: MemoryScope) -> GroundedAnswer:
        self.context_manager.append_turn(thread_id, scope, "user", query)
        bundle = self.context_manager.build_context(
            query, thread_id=thread_id, scope=scope, token_budget=240
        )
        memory_context = "\n".join(
            f"[{part.source}] {part.text}" for part in bundle.parts
        )
        answer = self.rag_answerer(query, scope.tenant_id, memory_context)
        self.context_manager.append_turn(thread_id, scope, "assistant", answer.text)
        return answer

    def remember(self, candidate: MemoryCandidate) -> WriteOutcome:
        return self.memory_gateway.remember(candidate)

