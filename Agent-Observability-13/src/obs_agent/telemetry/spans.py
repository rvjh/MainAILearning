from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SpanRecord(BaseModel):
    """OTel-inspired span fields for agent teaching (not a full SDK)."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: str = "internal"  # server | internal | client
    start_time: str
    end_time: str | None = None
    duration_ms: float | None = None
    status: str = "unset"  # unset | ok | error
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class ActiveSpan:
    record: SpanRecord
    started_perf: float


@dataclass
class TraceContext:
    trace_id: str
    job_id: str
    request_id: str
    attempt_id: str
    spans: list[SpanRecord] = field(default_factory=list)
    _stack: list[ActiveSpan] = field(default_factory=list)

    @property
    def current_span_id(self) -> str | None:
        return self._stack[-1].record.span_id if self._stack else None

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str = "internal",
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        record = SpanRecord(
            trace_id=self.trace_id,
            span_id=new_id("span"),
            parent_span_id=self.current_span_id,
            name=name,
            kind=kind,
            start_time=_now(),
            attributes=dict(attributes or {}),
        )
        active = ActiveSpan(record=record, started_perf=time.perf_counter())
        self._stack.append(active)
        try:
            yield record
            if record.status == "unset":
                record.status = "ok"
        except Exception as exc:
            record.status = "error"
            record.events.append({"name": "exception", "message": str(exc)})
            raise
        finally:
            record.end_time = _now()
            # Allow callers to override duration (e.g. measured tool latency).
            if record.duration_ms is None:
                record.duration_ms = (time.perf_counter() - active.started_perf) * 1000
            self.spans.append(record)
            self._stack.pop()


def start_trace(*, job_id: str, request_id: str, attempt_id: str) -> TraceContext:
    return TraceContext(
        trace_id=new_id("trace"),
        job_id=job_id,
        request_id=request_id,
        attempt_id=attempt_id,
    )
