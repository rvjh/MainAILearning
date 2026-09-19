#!/usr/bin/env python3
"""Telemetry primer — run BEFORE the agent labs.

Teaches logs / metrics / traces with a tiny non-agent example so the later
support-ops spans and dashboards are not a brand-new vocabulary.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.telemetry.metrics import MetricsRegistry
from obs_agent.telemetry.spans import start_trace
from obs_agent.telemetry.store import TelemetryStore


def brew_coffee(*, size: str, shots: int, slow_grinder: bool = False) -> dict:
    """Pretend cafe workflow — not an agent. Just enough to emit telemetry."""
    metrics = MetricsRegistry()
    store = TelemetryStore(export_path=None)
    ctx = start_trace(job_id="order_demo", request_id="req_demo", attempt_id="attempt_1")

    # LOG: a discrete event with a message (what happened)
    log_event = {
        "level": "info",
        "message": "order_received",
        "size": size,
        "shots": shots,
    }

    metrics.incr("orders_accepted")
    t0 = time.perf_counter()

    with ctx.span("cafe.order", kind="server", attributes={"order.size": size}):
        with ctx.span("cafe.grind", kind="internal", attributes={"shots": shots}) as grind:
            if slow_grinder:
                time.sleep(0.25)
            grind.attributes["grind.ok"] = True

        with ctx.span("cafe.extract", kind="internal"):
            time.sleep(0.05)

        with ctx.span("cafe.serve", kind="internal"):
            drink = f"{shots}-shot {size} espresso"

    elapsed_ms = (time.perf_counter() - t0) * 1000
    metrics.observe("order_latency_ms", elapsed_ms)
    metrics.incr("orders_completed")

    store.record_trace(ctx, extras={"drink": drink})

    # TRACE summary: related spans under one trace_id
    spans = [
        {
            "name": s.name,
            "parent": s.parent_span_id,
            "duration_ms": round(s.duration_ms or 0.0, 1),
            "span_id": s.span_id,
        }
        for s in ctx.spans
    ]
    dash = metrics.dashboard_view()
    # dashboard_view is agent-shaped; show raw counters/histograms for the primer
    snap = metrics.snapshot()

    return {
        "log": log_event,
        "metric": {
            "orders_accepted": snap.counters.get("orders_accepted", 0),
            "orders_completed": snap.counters.get("orders_completed", 0),
            "order_latency_ms": snap.histograms.get("order_latency_ms", {}),
        },
        "trace": {
            "trace_id": ctx.trace_id,
            "spans": spans,
        },
        "drink": drink,
        "note": "Same three signals appear later on the support-ops agent.",
    }


def main() -> int:
    print("=== Telemetry primer (before the agent) ===\n")
    print("Telemetry = the signals a running system emits so we can investigate it.")
    print("Three basic kinds:\n")
    print("  1. LOG     — one event, one message  (what happened?)")
    print("  2. METRIC  — aggregated numbers      (how often / how long?)")
    print("  3. TRACE   — related spans in one run (where did the time go?)\n")

    print("--- Fast order ---")
    fast = brew_coffee(size="small", shots=2, slow_grinder=False)
    print(json.dumps(fast, indent=2))

    print("\n--- Slow grinder (find the bottleneck from the TRACE) ---")
    slow = brew_coffee(size="large", shots=3, slow_grinder=True)
    print(json.dumps(slow, indent=2))

    grind = next(s for s in slow["trace"]["spans"] if s["name"] == "cafe.grind")
    extract = next(s for s in slow["trace"]["spans"] if s["name"] == "cafe.extract")
    assert grind["duration_ms"] > extract["duration_ms"]

    print("\nASK the room: which span dominated the slow order?")
    print(f"EVIDENCE: cafe.grind={grind['duration_ms']}ms vs cafe.extract={extract['duration_ms']}ms")
    print("\nNext: the support-ops agent uses the same ideas —")
    print("  logs/events, metrics dashboards, and traces with tool/model spans.")
    print("primer: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
