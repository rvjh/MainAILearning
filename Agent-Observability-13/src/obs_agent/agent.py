"""LangGraph support-ops agent with deterministic classroom scenarios.

Uses LangChain message types and a compiled LangGraph. LLM calls are optional;
fault scenarios drive the teaching demos without requiring API keys.
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from obs_agent.catalog import extract_order_id, lookup_order_record, policy_text
from obs_agent.config import Settings, get_settings
from obs_agent.contracts import FaultScenario, ToolCallRecord
from obs_agent.tools import ToolGateway


class AgentState(TypedDict, total=False):
    question: str
    order_id: str | None
    scenario: str
    tenant_id: str
    retrieve: dict[str, Any]
    plan: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    evidence: list[str]
    answer: str
    citations: list[str]
    steps: list[str]
    prompt_tokens: int
    completion_tokens: int
    model_latency_ms: float
    errors: list[str]


def _sleep_fn_from(settings_sleep: Callable[[float], None] | None) -> Callable[[float], None]:
    return settings_sleep or time.sleep


class SupportOpsAgent:
    """Customer support ops agent: retrieve → plan → tools → generate."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        gateway: ToolGateway | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sleep = _sleep_fn_from(sleep_fn)
        self.gateway = gateway or ToolGateway(
            allow_demo_faults=self.settings.allow_demo_faults,
            sleep_fn=self.sleep,
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("plan", self._plan)
        graph.add_node("tools", self._tools)
        graph.add_node("generate", self._generate)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "plan")
        graph.add_edge("plan", "tools")
        graph.add_edge("tools", "generate")
        graph.add_edge("generate", END)
        return graph.compile()

    def invoke(
        self,
        *,
        question: str,
        scenario: FaultScenario = FaultScenario.CORRECT,
        order_id: str | None = None,
        tenant_id: str = "tenant_acme",
    ) -> AgentState:
        oid = order_id or extract_order_id(question)
        return self.graph.invoke(
            {
                "question": question,
                "order_id": oid,
                "scenario": scenario.value,
                "tenant_id": tenant_id,
                "tool_calls": [],
                "evidence": [],
                "citations": [],
                "steps": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "model_latency_ms": 0.0,
                "errors": [],
            }
        )

    def _retrieve(self, state: AgentState) -> dict[str, Any]:
        scenario = FaultScenario(state.get("scenario", "correct"))
        order_id = state.get("order_id")
        policies = [policy_text("shipping"), policy_text("refund")]
        order = lookup_order_record(order_id) if order_id else None
        context_pad = ""
        if scenario == FaultScenario.OVERSIZED_CONTEXT:
            context_pad = ("PRIOR_TICKET_NOTE " * 400).strip()
        retrieve = {
            "order_id": order_id,
            "order": order,
            "policies": policies,
            "context_pad_chars": len(context_pad),
            "framework": "langgraph",
        }
        evidence = []
        if order:
            evidence.append(
                f"order:{order_id} status={order['status']} eta={order['eta']} "
                f"carrier={order['carrier']} tracking={order['tracking']}"
            )
        evidence.extend(f"policy:{p}" for p in policies)
        if context_pad:
            evidence.append(context_pad)
        return {
            "retrieve": retrieve,
            "evidence": evidence,
            "steps": list(state.get("steps") or []) + ["retrieve"],
        }

    def _plan(self, state: AgentState) -> dict[str, Any]:
        scenario = FaultScenario(state.get("scenario", "correct"))
        question = (state.get("question") or "").lower()
        order_id = state.get("order_id")
        actions: list[str] = []
        if order_id and ("status" in question or "where" in question or "track" in question or "eta" in question):
            actions.append("lookup_order")
            actions.append("get_policy:shipping")
        elif "refund" in question:
            actions.append("lookup_order")
            actions.append("get_policy:refund")
        elif "ticket" in question:
            actions.append("create_ticket")
        else:
            actions.append("lookup_order")
            actions.append("get_policy:support")

        if scenario == FaultScenario.TOOL_LOOP:
            actions = ["lookup_order", "lookup_order", "lookup_order", "lookup_order", "lookup_order"]
        if scenario == FaultScenario.BUDGET_BREACH_SUCCESS:
            actions = ["lookup_order", "get_policy:shipping", "get_policy:refund", "get_policy:support", "lookup_order"]
        if scenario == FaultScenario.DENIED_TOOL:
            actions = ["create_ticket"]

        plan = {
            "goal": state.get("question"),
            "actions": actions,
            "framework": "langgraph",
            "provider": "deterministic",
        }
        # Optional real model planning when key present and scenario wants it.
        if self.settings.use_llm:
            plan["provider"] = f"langchain_openai:{self.settings.openai_model}"
        return {
            "plan": plan,
            "steps": list(state.get("steps") or []) + ["plan"],
        }

    def _tools(self, state: AgentState) -> dict[str, Any]:
        scenario = FaultScenario(state.get("scenario", "correct"))
        plan = state.get("plan") or {}
        actions = list(plan.get("actions") or [])
        order_id = state.get("order_id") or "ORD-1001"
        records: list[ToolCallRecord] = []
        evidence = list(state.get("evidence") or [])
        errors = list(state.get("errors") or [])

        for action in actions:
            if action.startswith("get_policy:"):
                topic = action.split(":", 1)[1]
                name, args = "get_policy", {"topic": topic}
            elif action == "lookup_order":
                name, args = "lookup_order", {"order_id": order_id}
            elif action == "create_ticket":
                name, args = "create_ticket", {
                    "priority": "P3",
                    "summary": state.get("question") or "support request",
                }
            else:
                continue

            attempt = 1
            record = self.gateway.execute(name, args, scenario=scenario, attempt=attempt)
            if (
                not record.ok
                and record.output == "transient_timeout"
                and scenario == FaultScenario.TRANSIENT_TOOL_ERROR
            ):
                retry = self.gateway.execute(name, args, scenario=FaultScenario.NONE, attempt=2)
                records.append(record)
                records.append(retry)
                record = retry
            else:
                records.append(record)

            if record.ok:
                evidence.append(record.output)
            else:
                errors.append(f"{record.name}:{record.output}")

        return {
            "tool_calls": [r.model_dump() for r in records],
            "evidence": evidence,
            "errors": errors,
            "steps": list(state.get("steps") or []) + ["tools"],
        }

    def _generate(self, state: AgentState) -> dict[str, Any]:
        scenario = FaultScenario(state.get("scenario", "correct"))
        order_id = state.get("order_id")
        order = (state.get("retrieve") or {}).get("order")
        evidence = list(state.get("evidence") or [])
        citations = [e for e in evidence if e.startswith("order:") or e.startswith("policy:") or e.startswith("Order ")]
        started = time.perf_counter()

        if scenario == FaultScenario.SLOW_MODEL:
            self.sleep(0.40)

        if scenario in {FaultScenario.CONFIDENTLY_WRONG, FaultScenario.UNSUPPORTED_CLAIM}:
            # Technically successful completion, factually wrong / ungrounded.
            answer = (
                f"Order {order_id} was delivered on 2026-12-25 via magic drone. "
                "No need to worry — everything is fine."
            )
            # Keep a citation-looking string so schema validation can pass while
            # groundedness fails (opening demo + quality lab).
            if scenario == FaultScenario.UNSUPPORTED_CLAIM:
                citations = citations[:1] or ["policy:shipping note"]
            else:
                citations = citations[:1] or ["order:fabricated"]
        elif scenario == FaultScenario.DENIED_TOOL:
            answer = "I could not create a ticket because the tool call was denied by policy."
            citations = ["policy:support"]
        elif order:
            answer = (
                f"Order {order_id} status is {order['status']} with ETA {order['eta']}. "
                f"Carrier={order['carrier']}, tracking={order['tracking']}."
            )
        else:
            answer = "I could not find that order. Please provide a valid order id like ORD-1001."

        # Optional real LLM polish (still constrained by evidence in prompt).
        prompt_tokens = max(8, len(state.get("question") or "") // 4 + len(" ".join(evidence)) // 4)
        completion_tokens = max(4, len(answer) // 4)
        if scenario == FaultScenario.OVERSIZED_CONTEXT:
            prompt_tokens += 2500
        if scenario == FaultScenario.BUDGET_BREACH_SUCCESS:
            prompt_tokens += 800
            completion_tokens += 400

        model_latency_ms = (time.perf_counter() - started) * 1000
        if scenario == FaultScenario.SLOW_MODEL:
            model_latency_ms = max(model_latency_ms, 400.0)

        errors = list(state.get("errors") or [])
        # Live OpenAI only on non-fault teaching paths so injected failures stay reproducible.
        live_scenarios = {
            FaultScenario.CORRECT,
            FaultScenario.NONE,
            FaultScenario.TRANSIENT_TOOL_ERROR,
        }
        if self.settings.use_llm and scenario in live_scenarios:
            try:
                answer = self._llm_answer(question=state.get("question") or "", evidence=evidence)
                completion_tokens = max(completion_tokens, len(answer) // 4)
                model_latency_ms = (time.perf_counter() - started) * 1000
            except Exception as exc:  # noqa: BLE001
                errors.append(f"model_fallback:{exc}")

        return {
            "answer": answer,
            "citations": citations,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model_latency_ms": model_latency_ms,
            "errors": errors,
            "steps": list(state.get("steps") or []) + ["generate"],
        }

    def _llm_answer(self, *, question: str, evidence: list[str]) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=self.settings.openai_model,
            api_key=self.settings.openai_api_key,
            temperature=0,
        )
        msg = model.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a concise support ops agent. Answer ONLY using the "
                        "evidence list. If evidence is missing, say so. Cite order ids."
                    )
                ),
                HumanMessage(
                    content=f"Question: {question}\nEvidence:\n- " + "\n- ".join(evidence[:12])
                ),
            ]
        )
        content = msg.content
        if isinstance(content, list):
            return "".join(str(part) for part in content).strip()
        return str(content or "").strip()
