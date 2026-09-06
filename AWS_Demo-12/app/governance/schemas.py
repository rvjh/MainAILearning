"""Governance Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionClass(str, Enum):
    READ = "read"
    WRITE = "write"
    HIGH_RISK_WRITE = "high_risk_write"
    DESTRUCTIVE = "destructive"


class TargetSystem(str, Enum):
    DEPLOY_CATALOG = "deploy_catalog"
    OPENAI = "openai"


class PolicyDecisionType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class AuditStatus(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    PENDING_APPROVAL = "pending_approval"
    EXECUTED = "executed"
    FAILED = "failed"


class AgentContext(BaseModel):
    agent_id: str
    agent_run_id: str
    user_id: str
    user_role: str = "platform_engineer"
    data_classification: str = "internal"
    outside_business_hours: bool = False
    environment: str = "demo"


class ProposedAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    agent_run_id: str
    user_id: str
    tool_name: str
    action_class: ActionClass
    target_system: TargetSystem
    resource_type: str
    resource_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ToolDefinition(BaseModel):
    tool_name: str
    action_class: ActionClass
    target_system: TargetSystem
    default_policy: str
    allowed_fields: list[str] = Field(default_factory=list)
    blocked_fields: list[str] = Field(default_factory=list)
    approval_required: bool = False
    audit_required: bool = True
    description: str = ""


class PolicyDecision(BaseModel):
    decision: PolicyDecisionType
    reason: str
    risk_score: int = 0
    required_approval_type: Optional[str] = None
    allowed_scope: list[str] = Field(default_factory=list)
    ttl_seconds: int = 300


class JITToken(BaseModel):
    token_id: str = Field(default_factory=lambda: str(uuid4()))
    token_value: str
    issued_to: str
    tool_name: str
    scope: list[str] = Field(default_factory=list)
    resource_id: str
    allowed_fields: list[str] = Field(default_factory=list)
    ttl_seconds: int
    expires_at: datetime
    risk_score: int = 0


class ToolResult(BaseModel):
    success: bool
    status: str
    tool_name: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    policy_decision: Optional[PolicyDecision] = None
    jit_token: Optional[JITToken] = None


class ApprovalResult(BaseModel):
    approved: bool = False
    pending: bool = False
    approval_id: str = ""
    approver: Optional[str] = None
    reason: str = ""


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.utcnow())
    agent_id: str
    agent_run_id: str
    user_id: str
    tool_name: str
    target_system: str
    action_class: str
    resource_type: str
    resource_id: str
    args_redacted: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    policy_decision: str
    risk_score: int = 0
    approval_required: bool = False
    approval_id: Optional[str] = None
    jit_token_id: Optional[str] = None
    status: AuditStatus
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
