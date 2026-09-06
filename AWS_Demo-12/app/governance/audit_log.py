"""Append-only JSONL audit log."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import AUDIT_LOG_PATH, ensure_data_dir
from app.governance.schemas import AuditEvent, AuditStatus

SENSITIVE_FIELDS = {"api_key", "token", "password", "openai_api_key", "secret"}


def redact_args(args: dict[str, Any]) -> dict[str, Any]:
    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                key: "***REDACTED***" if key in SENSITIVE_FIELDS else walk(value)
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [walk(item) for item in obj]
        return obj

    return walk(args)


def record_audit_event(
    *,
    agent_id: str,
    agent_run_id: str,
    user_id: str,
    tool_name: str,
    target_system: str,
    action_class: str,
    resource_type: str,
    resource_id: str,
    args: dict[str, Any],
    reason: str,
    policy_decision: str,
    risk_score: int = 0,
    approval_required: bool = False,
    approval_id: str | None = None,
    jit_token_id: str | None = None,
    status: AuditStatus,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> AuditEvent:
    ensure_data_dir()
    event = AuditEvent(
        event_id=str(uuid4()),
        timestamp_utc=datetime.utcnow(),
        agent_id=agent_id,
        agent_run_id=agent_run_id,
        user_id=user_id,
        tool_name=tool_name,
        target_system=target_system,
        action_class=action_class,
        resource_type=resource_type,
        resource_id=resource_id,
        args_redacted=redact_args(args),
        reason=reason,
        policy_decision=policy_decision,
        risk_score=risk_score,
        approval_required=approval_required,
        approval_id=approval_id,
        jit_token_id=jit_token_id,
        status=status,
        before=before,
        after=after,
        error=error,
        duration_ms=duration_ms,
    )
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")
    return event


def read_audit_events(path: Path | None = None) -> list[AuditEvent]:
    log_path = path or AUDIT_LOG_PATH
    if not log_path.exists():
        return []
    events: list[AuditEvent] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(AuditEvent.model_validate_json(line))
    return events
