from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class HealthDimension(str, Enum):
    RELIABILITY = "reliability"
    PERFORMANCE = "performance"
    QUALITY = "quality"
    EFFICIENCY = "efficiency"
    SAFETY = "safety"


class FaultScenario(str, Enum):
    NONE = "none"
    CORRECT = "correct"
    CONFIDENTLY_WRONG = "confidently_wrong"
    SLOW_TOOL = "slow_tool"
    SLOW_MODEL = "slow_model"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    TOOL_LOOP = "tool_loop"
    OVERSIZED_CONTEXT = "oversized_context"
    DENIED_TOOL = "denied_tool"
    TRANSIENT_TOOL_ERROR = "transient_tool_error"
    BUDGET_BREACH_SUCCESS = "budget_breach_success"
    STUCK_HEARTBEAT = "stuck_heartbeat"


class RunRequest(BaseModel):
    question: str
    tenant_id: str = "tenant_acme"
    user_id: str = "user_demo"
    order_id: str | None = None
    scenario: FaultScenario = FaultScenario.CORRECT
    metadata: dict[str, str] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    output: str
    ok: bool
    denied: bool = False
    latency_ms: float = 0.0
    attempt: int = 1


class ValidationResult(BaseModel):
    ok: bool
    checks: dict[str, bool]
    failures: list[str] = Field(default_factory=list)


class HealthScorecard(BaseModel):
    reliability: bool
    performance: bool
    quality: bool
    efficiency: bool
    safety: bool
    notes: dict[str, str] = Field(default_factory=dict)

    @property
    def all_healthy(self) -> bool:
        return all(
            [
                self.reliability,
                self.performance,
                self.quality,
                self.efficiency,
                self.safety,
            ]
        )


class RunResult(BaseModel):
    job_id: str
    request_id: str
    attempt_id: str
    trace_id: str
    status: JobStatus
    answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    queue_wait_ms: float = 0.0
    execution_ms: float = 0.0
    end_to_end_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    validation: ValidationResult | None = None
    grounded: bool | None = None
    business_success: bool = False
    health: HealthScorecard | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    budget_ok: bool = True
    budget_failures: list[str] = Field(default_factory=list)
    alert_fired: list[str] = Field(default_factory=list)
    redacted_export_ok: bool = True


ScenarioName = Literal[
    "none",
    "correct",
    "confidently_wrong",
    "slow_tool",
    "slow_model",
    "unsupported_claim",
    "tool_loop",
    "oversized_context",
    "denied_tool",
    "transient_tool_error",
    "budget_breach_success",
    "stuck_heartbeat",
]
