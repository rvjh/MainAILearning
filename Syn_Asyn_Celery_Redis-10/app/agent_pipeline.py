"""LangGraph agent workflow + LangChain ChatOpenAI (no OpenAI SDK).

Worker still advances one checkpointed step at a time. Each step is a LangGraph node.
"""

from __future__ import annotations

import json
import time
import warnings
from typing import Any, TypedDict

# LangGraph currently warns on import until it sets allowed_objects explicitly.
warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change in a future version.*",
)

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.contracts import JobRecord
from app.errors import MemoryRejected, PermanentFailure, TransientFailure
from app.memory import GovernedMemoryGateway


class AgentState(TypedDict, total=False):
    job_id: str
    tenant_id: str
    user_id: str
    prompt: str
    thread_id: str
    metadata: dict[str, str]
    attempts: int
    retrieve: dict[str, Any]
    plan: dict[str, Any]
    execute: dict[str, Any]
    persist: dict[str, Any]


def _chat_model():
    """LangChain OpenAI chat model — used only when OPENAI_API_KEY is set."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def _llm_text(*, system: str, user: str) -> str:
    try:
        model = _chat_model()
        response = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = response.content
        if isinstance(content, list):
            return "".join(str(part) for part in content).strip()
        return str(content or "").strip()
    except Exception as exc:
        raise TransientFailure(f"langchain_openai_transient:{exc}") from exc


def _llm_json(*, system: str, user: str) -> dict[str, Any]:
    text = _llm_text(system=system, user=user)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Ask model once more for JSON-only if free text returned.
        repaired = _llm_text(
            system="Return only valid JSON. No markdown.",
            user=f"Convert to JSON object:\n{text}",
        )
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return {"raw": text}


def _job_fields(job: JobRecord) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "user_id": job.user_id,
        "prompt": str(job.payload.get("prompt", "")),
        "thread_id": str(job.payload.get("thread_id", "")),
        "metadata": dict(job.payload.get("metadata") or {}),
        "attempts": job.attempts,
    }


class AgentPipeline:
    """Exposes LangGraph nodes as checkpointable steps for the Celery worker."""

    steps = ("retrieve", "plan", "execute", "persist")

    def __init__(self, memory: GovernedMemoryGateway | None = None) -> None:
        self.memory = memory or GovernedMemoryGateway()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("retrieve", self._node_retrieve)
        graph.add_node("plan", self._node_plan)
        graph.add_node("execute", self._node_execute)
        graph.add_node("persist", self._node_persist)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "persist")
        graph.add_edge("persist", END)
        return graph.compile()

    def run_step(self, job: JobRecord, step: str, prior: dict[str, Any]) -> dict[str, Any]:
        """Run one LangGraph node (supports worker checkpoint resume)."""
        state: AgentState = {**_job_fields(job), **{k: v for k, v in prior.items() if k in self.steps}}
        settings = get_settings()
        metadata = state.get("metadata") or {}
        if settings.allow_demo_faults and metadata.get("demo_pause_step") == step:
            pause = min(max(float(metadata.get("demo_pause_seconds", "0")), 0.0), 10.0)
            time.sleep(pause)
        if step == "retrieve":
            return self._node_retrieve(state)["retrieve"]
        if step == "plan":
            return self._node_plan(state)["plan"]
        if step == "execute":
            return self._node_execute(state)["execute"]
        if step == "persist":
            return self._node_persist(state)["persist"]
        raise ValueError(f"unknown step: {step}")

    def run_graph(self, job: JobRecord) -> AgentState:
        """Full LangGraph invoke (no per-step checkpointing)."""
        return self.graph.invoke(_job_fields(job))

    def _node_retrieve(self, state: AgentState) -> dict[str, Any]:
        memories = self.memory.recall(
            tenant_id=state["tenant_id"],
            user_id=state["user_id"],
            agent_id="support-agent",
            purpose="customer_support",
            query=state.get("prompt", ""),
            limit=3,
        )
        return {
            "retrieve": {
                "step": "retrieve",
                "memories": memories,
                "thread_id": state.get("thread_id"),
                "prompt": state.get("prompt"),
                "framework": "langgraph",
            }
        }

    def _node_plan(self, state: AgentState) -> dict[str, Any]:
        retrieve = state.get("retrieve") or {}
        memory_lines = [f"- {m['key']}: {m['value']}" for m in retrieve.get("memories", [])]
        plan: dict[str, Any] = {
            "goal": state.get("prompt"),
            "memory_context": memory_lines,
            "actions": ["ground_answer", "propose_memory_if_supported"],
            "framework": "langgraph",
        }
        settings = get_settings()
        if settings.openai_api_key:
            plan["llm"] = _llm_json(
                system=(
                    "You are a support agent planner using LangChain ChatOpenAI. "
                    "Return compact JSON with keys goal and steps (array of strings)."
                ),
                user=json.dumps({"prompt": state.get("prompt"), "memories": memory_lines}),
            )
            plan["provider"] = f"langchain_openai:{settings.openai_model}"
        else:
            plan["provider"] = "deterministic"
        return {"plan": {"step": "plan", "plan": plan}}

    def _node_execute(self, state: AgentState) -> dict[str, Any]:
        settings = get_settings()
        metadata = state.get("metadata") or {}
        if settings.allow_demo_faults:
            transient_failures = int(metadata.get("demo_transient_failures", "0"))
            if int(state.get("attempts", 0)) <= transient_failures:
                raise TransientFailure("demo_transient_timeout")
            if metadata.get("demo_permanent_failure", "false").casefold() == "true":
                raise PermanentFailure("demo_invalid_request")

        plan_wrap = state.get("plan") or {}
        plan = plan_wrap.get("plan") or {}
        memory_bits = "; ".join(plan.get("memory_context") or [])
        answer = (
            f"Grounded response for thread {state.get('thread_id')}: "
            f"{state.get('prompt')}"
        )
        if memory_bits:
            answer += f" Using remembered context: {memory_bits}"

        model_label = "deterministic"
        if settings.openai_api_key:
            answer = _llm_text(
                system=(
                    "You are a support agent. Answer briefly using only the provided "
                    "memory context. Do not invent preferences. Powered by LangChain ChatOpenAI."
                ),
                user=json.dumps({"prompt": state.get("prompt"), "memory": memory_bits or "none"}),
            )
            model_label = f"langchain_openai:{settings.openai_model}"
        return {
            "execute": {
                "step": "execute",
                "answer": answer,
                "model": model_label,
                "framework": "langgraph",
            }
        }

    def _node_persist(self, state: AgentState) -> dict[str, Any]:
        """Governed memory write — model proposes, policy decides (Saturday rule)."""
        prompt = str(state.get("prompt", ""))
        metadata = state.get("metadata") or {}
        preference = metadata.get("contact_preference")
        stored = None
        rejected = None
        if preference:
            try:
                stored = self.memory.remember(
                    tenant_id=state["tenant_id"],
                    user_id=state["user_id"],
                    agent_id="support-agent",
                    purpose="customer_support",
                    subject=state["user_id"],
                    key="contact_preference",
                    value=preference,
                    source_kind="user_asserted",
                    source_id=state["job_id"],
                    evidence_excerpt=f"User metadata contact_preference={preference}; prompt={prompt[:120]}",
                    verified=True,
                    confidence=0.98,
                )
            except MemoryRejected as exc:
                rejected = str(exc)
        try:
            self.memory.remember(
                tenant_id=state["tenant_id"],
                user_id=state["user_id"],
                agent_id="support-agent",
                purpose="customer_support",
                subject=state["user_id"],
                key="inferred_mood",
                value="frustrated",
                source_kind="model_inference",
                source_id=state["job_id"],
                evidence_excerpt="model tone guess",
                verified=False,
                confidence=0.99,
            )
        except MemoryRejected as exc:
            rejected = (rejected + ";" if rejected else "") + str(exc)

        execute = state.get("execute") or {}
        return {
            "persist": {
                "step": "persist",
                "answer": execute.get("answer"),
                "memory_write": stored,
                "memory_rejected": rejected,
                "framework": "langgraph",
            }
        }
