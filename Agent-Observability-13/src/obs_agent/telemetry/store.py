from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from obs_agent.telemetry.spans import SpanRecord, TraceContext


@dataclass
class TelemetryStore:
    """In-memory store + optional JSONL export for classroom dashboards."""

    traces: list[dict[str, Any]] = field(default_factory=list)
    spans: list[SpanRecord] = field(default_factory=list)
    export_path: Path | None = None

    def record_trace(self, ctx: TraceContext, *, extras: dict[str, Any] | None = None) -> None:
        payload = {
            "trace_id": ctx.trace_id,
            "job_id": ctx.job_id,
            "request_id": ctx.request_id,
            "attempt_id": ctx.attempt_id,
            "spans": [s.model_dump() for s in ctx.spans],
            **(extras or {}),
        }
        self.traces.append(payload)
        self.spans.extend(ctx.spans)
        if self.export_path is not None:
            self.export_path.parent.mkdir(parents=True, exist_ok=True)
            with self.export_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload) + "\n")

    def spans_by_name(self) -> dict[str, list[SpanRecord]]:
        grouped: dict[str, list[SpanRecord]] = defaultdict(list)
        for span in self.spans:
            grouped[span.name].append(span)
        return dict(grouped)

    def clear(self) -> None:
        self.traces.clear()
        self.spans.clear()
