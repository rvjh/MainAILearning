from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricSnapshot:
    counters: dict[str, float]
    gauges: dict[str, float]
    histograms: dict[str, dict[str, float]]


@dataclass
class MetricsRegistry:
    """Teaching metrics: counters, gauges, histograms (no user_id labels)."""

    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    gauges: dict[str, float] = field(default_factory=dict)
    _hist: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def incr(self, name: str, value: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        key = self._key(name, labels)
        self.counters[key] += value

    def set_gauge(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        self.gauges[self._key(name, labels)] = value

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        self._hist[self._key(name, labels)].append(value)

    def snapshot(self) -> MetricSnapshot:
        histograms: dict[str, dict[str, float]] = {}
        for key, values in self._hist.items():
            histograms[key] = self._summarize(values)
        return MetricSnapshot(
            counters=dict(self.counters),
            gauges=dict(self.gauges),
            histograms=histograms,
        )

    def dashboard_view(self) -> dict[str, Any]:
        snap = self.snapshot()

        def counter_sum(prefix: str) -> float:
            total = 0.0
            for key, value in snap.counters.items():
                if key == prefix or key.startswith(prefix + "|"):
                    total += value
            return total

        return {
            "jobs": {
                "accepted": counter_sum("jobs_accepted"),
                "completed": counter_sum("jobs_completed"),
                "failed": counter_sum("jobs_failed"),
                "cancelled": counter_sum("jobs_cancelled"),
                "overdue": counter_sum("jobs_overdue"),
            },
            "latency_ms": {
                "end_to_end": snap.histograms.get("latency_end_to_end_ms", {}),
                "queue_wait": snap.histograms.get("latency_queue_wait_ms", {}),
                "execution": snap.histograms.get("latency_execution_ms", {}),
            },
            "tools": {
                "errors": {
                    k: v
                    for k, v in snap.counters.items()
                    if k.startswith("tool_errors|")
                },
                "timeouts": {
                    k: v
                    for k, v in snap.counters.items()
                    if k.startswith("tool_timeouts|")
                },
                "calls": {
                    k: v
                    for k, v in snap.counters.items()
                    if k.startswith("tool_calls|")
                },
            },
            "model": {
                "errors": counter_sum("model_errors"),
                "rate_limits": counter_sum("model_rate_limits"),
                "fallbacks": counter_sum("model_fallbacks"),
            },
            "quality": {
                "validated_success": counter_sum("validated_success"),
                "validated_failure": counter_sum("validated_failure"),
                "eval_coverage": snap.gauges.get("eval_coverage", 0.0),
            },
            "cost": {
                "estimated_usd_total": counter_sum("estimated_cost_usd"),
                "tokens_in": counter_sum("tokens_in"),
                "tokens_out": counter_sum("tokens_out"),
            },
            "versions": {
                k: v
                for k, v in snap.counters.items()
                if k.startswith("jobs_completed|agent_version=")
                or k.startswith("validated_success|agent_version=")
                or k.startswith("validated_failure|agent_version=")
            },
        }

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        # Refuse high-cardinality identity labels in teaching code.
        banned = {"user_id", "request_id", "job_id", "trace_id"}
        safe = {k: v for k, v in labels.items() if k not in banned}
        if not safe:
            return name
        suffix = "|".join(f"{k}={v}" for k, v in sorted(safe.items()))
        return f"{name}|{suffix}"

    @staticmethod
    def _summarize(values: list[float]) -> dict[str, float]:
        if not values:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
        ordered = sorted(values)

        def pct(p: float) -> float:
            if len(ordered) == 1:
                return ordered[0]
            idx = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
            return ordered[idx]

        return {
            "count": float(len(ordered)),
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "avg": sum(ordered) / len(ordered),
        }
