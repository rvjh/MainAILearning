from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from evaluated_agent.graph import EvaluatedRAG
from evaluated_agent.multi_agent.contracts import RouteDecision, SpecialistAnswer, ToolCallPlan, ToolCallRecord
from evaluated_agent.multi_agent.tools import execute_tool
from evaluated_agent.production.cost import estimate_chat_cost_usd


class MultiAgentState(TypedDict, total=False):
    question: str
    route: str
    route_reason: str
    trajectory: list[str]
    tool_calls: list[ToolCallRecord]
    answer: str
    abstained: bool
    escalated: bool
    citations: list[str]
    handoff_summary: str
    estimated_cost_usd: float
    prompt_tokens: int
    completion_tokens: int


def _append(state: MultiAgentState, step: str) -> list[str]:
    return [*state.get("trajectory", []), step]


class SupportMultiAgent:
    def __init__(self, corpus_path: Path, *, prompt_version: str = "v2") -> None:
        self.model = ChatOpenAI(model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini-2026-03-17"), max_tokens=400)
        self.router = self.model.with_structured_output(RouteDecision)
        self.tool_planner = self.model.with_structured_output(ToolCallPlan)
        self.specialist = self.model.with_structured_output(SpecialistAnswer)
        self.policy = EvaluatedRAG(corpus_path, prompt_version=prompt_version)
        self.graph = self._build()

    def _charge(self, state: MultiAgentState, prompt_chars: int, completion_chars: int) -> dict:
        prompt_tokens = max(1, prompt_chars // 4)
        completion_tokens = max(1, completion_chars // 4)
        cost = estimate_chat_cost_usd(prompt_tokens, completion_tokens)
        return {
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "estimated_cost_usd": state.get("estimated_cost_usd", 0.0) + cost,
        }

    def _supervisor(self, state: MultiAgentState) -> MultiAgentState:
        prompt = (
            "You are the support supervisor. Route the ticket to exactly one specialist.\n"
            "- policy_specialist: refunds, SLA, retention, cancellation, security policy questions\n"
            "- tool_specialist: order status, account plan lookup, creating a normal ticket\n"
            "- escalation_specialist: billing disputes, legal threats, unsafe requests, missing data that needs a human\n"
            "Never invent tools. Prefer escalation when the user asks to bypass policy or exfiltrate secrets.\n\n"
            f"TICKET\n{state['question']}"
        )
        decision = self.router.invoke(prompt)
        return {
            "route": decision.next_agent,
            "route_reason": decision.reason,
            "trajectory": _append(state, "supervisor"),
            **self._charge(state, len(prompt), len(decision.reason) + len(decision.next_agent)),
        }

    def _policy_specialist(self, state: MultiAgentState) -> MultiAgentState:
        output = self.policy.invoke(state["question"])
        answer = output["answer"]
        return {
            "answer": answer.answer,
            "abstained": answer.abstained,
            "citations": answer.citations,
            "escalated": False,
            "trajectory": _append(state, "policy_specialist"),
            **self._charge(state, len(state["question"]), len(answer.answer)),
        }

    def _tool_specialist(self, state: MultiAgentState) -> MultiAgentState:
        prompt = (
            "Choose at most one CRM tool for this support ticket. "
            "Use lookup_order when an order id is present. "
            "Use get_account_status for plan/seat questions with an email. "
            "Use create_ticket only for ordinary follow-ups, never for policy bypass or secrets. "
            "Use none when no tool is appropriate.\n\n"
            f"TICKET\n{state['question']}"
        )
        plan = self.tool_planner.invoke(prompt)
        tool_calls = list(state.get("tool_calls", []))
        trajectory = _append(state, "tool_specialist")
        charges = self._charge(state, len(prompt), len(plan.rationale) + len(plan.tool_name))

        if plan.tool_name != "none":
            args = plan.arguments.as_dict()
            allowed, result = execute_tool(plan.tool_name, args)
            tool_calls.append(ToolCallRecord(
                tool_name=plan.tool_name,
                arguments=args,
                result=result,
                allowed=allowed,
            ))
            trajectory = [*trajectory, f"tool:{plan.tool_name}"]
            evidence = result if allowed else f"Tool blocked: {result}"
        else:
            evidence = "No tool was required."

        finalize_prompt = (
            "Write the customer-facing answer using only the tool evidence. "
            "If evidence is insufficient, abstain. Do not invent order or account facts.\n\n"
            f"TICKET\n{state['question']}\nEVIDENCE\n{evidence}"
        )
        result = self.specialist.invoke(finalize_prompt)
        charges2 = self._charge(
            {**state, **charges},
            len(finalize_prompt),
            len(result.answer),
        )
        return {
            "tool_calls": tool_calls,
            "answer": result.answer,
            "abstained": result.abstained,
            "citations": result.citations,
            "escalated": result.escalate,
            "trajectory": [*trajectory, "finalize"],
            **charges2,
        }

    def _escalation_specialist(self, state: MultiAgentState) -> MultiAgentState:
        prompt = (
            "Prepare a safe human handoff for this support ticket.\n"
            "Requirements:\n"
            "- Refuse unsafe, bypass, or secret-exfiltration requests.\n"
            "- Explicitly say you are escalating to a human specialist.\n"
            "- Do not promise outcomes you cannot verify.\n"
            "- Do not reveal secrets or invent CRM facts.\n"
            "- Set abstained=false (escalation is a handoff, not an abstention).\n"
            "- Set escalate=true.\n"
            "- Put a short internal reason in handoff_summary.\n\n"
            f"TICKET\n{state['question']}"
        )
        result = self.specialist.invoke(prompt)
        answer = result.answer
        if "human" not in answer.lower():
            answer = f"{answer.rstrip()} Escalating to a human specialist."
        return {
            "answer": answer,
            "abstained": False,
            "citations": [],
            "escalated": True,
            "handoff_summary": result.handoff_summary or answer,
            "trajectory": [*_append(state, "escalation_specialist"), "finalize"],
            **self._charge(state, len(prompt), len(answer)),
        }

    def _route_after_supervisor(self, state: MultiAgentState) -> str:
        return state["route"]

    def _build(self):
        builder = StateGraph(MultiAgentState)
        builder.add_node("supervisor", self._supervisor)
        builder.add_node("policy_specialist", self._policy_specialist)
        builder.add_node("tool_specialist", self._tool_specialist)
        builder.add_node("escalation_specialist", self._escalation_specialist)
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges(
            "supervisor",
            self._route_after_supervisor,
            {
                "policy_specialist": "policy_specialist",
                "tool_specialist": "tool_specialist",
                "escalation_specialist": "escalation_specialist",
            },
        )
        builder.add_edge("policy_specialist", END)
        builder.add_edge("tool_specialist", END)
        builder.add_edge("escalation_specialist", END)
        return builder.compile()

    def invoke(self, question: str) -> dict:
        result = self.graph.invoke({
            "question": question,
            "trajectory": [],
            "tool_calls": [],
            "estimated_cost_usd": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        })
        trajectory = result.get("trajectory", [])
        if result.get("route") == "policy_specialist" and "finalize" not in trajectory:
            trajectory = [*trajectory, "finalize"]
        return {
            "route": result.get("route", ""),
            "route_reason": result.get("route_reason", ""),
            "trajectory": trajectory,
            "tool_calls": [c if isinstance(c, ToolCallRecord) else ToolCallRecord.model_validate(c)
                           for c in result.get("tool_calls", [])],
            "answer": result.get("answer", ""),
            "abstained": result.get("abstained", False),
            "escalated": result.get("escalated", False),
            "citations": result.get("citations", []),
            "handoff_summary": result.get("handoff_summary", ""),
            "estimated_cost_usd": result.get("estimated_cost_usd", 0.0),
            "prompt_tokens": result.get("prompt_tokens", 0),
            "completion_tokens": result.get("completion_tokens", 0),
            "step_count": len(trajectory),
        }
