from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contracts import JudgeVerdict


AgentName = Literal["supervisor", "policy_specialist", "tool_specialist", "escalation_specialist", "finalize"]
RouteTarget = Literal["policy_specialist", "tool_specialist", "escalation_specialist"]


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_agent: RouteTarget = Field(description="Specialist to invoke for this ticket")
    reason: str = Field(description="Short routing rationale")


class ToolArguments(BaseModel):
    """Fixed-key tool args for OpenAI structured output (no free-form dicts)."""

    model_config = ConfigDict(extra="forbid")

    order_id: str = ""
    email: str = ""
    priority: str = ""
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v}


class ToolCallPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: Literal["lookup_order", "create_ticket", "get_account_status", "none"]
    arguments: ToolArguments = Field(default_factory=ToolArguments)
    rationale: str = ""


class SpecialistAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    abstained: bool = False
    citations: list[str] = Field(default_factory=list)
    escalate: bool = False
    handoff_summary: str = ""


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: str
    allowed: bool = True


class MultiAgentGoldenCase(BaseModel):
    case_id: str
    split: Literal["smoke", "full"]
    question: str
    reference_answer: str
    expected_route: RouteTarget
    expected_trajectory: list[str]
    expected_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    should_abstain: bool = False
    should_escalate: bool = False
    max_steps: int = 6
    max_tool_calls: int = 2
    max_cost_usd: float = 0.05


class MultiAgentCaseResult(BaseModel):
    case_id: str
    route: str
    trajectory: list[str]
    tool_calls: list[ToolCallRecord]
    answer: str
    abstained: bool
    escalated: bool
    citations: list[str]
    route_pass: bool
    tool_pass: bool
    trajectory_pass: bool
    contract_pass: bool
    budget_pass: bool
    safety_pass: bool
    judge: JudgeVerdict | None = None
    judge_score: float = 0.0
    estimated_cost_usd: float = 0.0
    step_count: int = 0
    passed: bool
    failures: list[str]
