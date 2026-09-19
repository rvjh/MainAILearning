from __future__ import annotations

from dataclasses import replace

from obs_agent.config import get_settings
from obs_agent.contracts import FaultScenario, RunRequest
from obs_agent.runtime import ObservabilityRuntime
from obs_agent.telemetry.metrics import MetricsRegistry
from obs_agent.telemetry.redact import redact_payload
from obs_agent.telemetry.spans import start_trace


def test_parent_child_spans():
    ctx = start_trace(job_id="j1", request_id="r1", attempt_id="a1")
    with ctx.span("parent"):
        with ctx.span("child"):
            pass
    assert len(ctx.spans) == 2
    child = next(s for s in ctx.spans if s.name == "child")
    parent = next(s for s in ctx.spans if s.name == "parent")
    assert child.parent_span_id == parent.span_id


def test_metrics_reject_user_id_label():
    m = MetricsRegistry()
    m.incr("jobs_completed", labels={"user_id": "u1", "agent_version": "v1"})
    snap = m.snapshot()
    assert "jobs_completed|agent_version=v1" in snap.counters
    assert "user_id" not in "".join(snap.counters)


def test_redaction():
    cleaned = redact_payload(
        {"question": "email me at a@b.com with sk-abcdefghijklmnopqrstuvwxyz123456"},
        capture_full_prompts=False,
    )
    blob = str(cleaned)
    assert "[REDACTED]" in blob
    assert "a@b.com" not in blob
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in blob


def test_trace_export_and_bottleneck():
    settings = replace(get_settings(), openai_api_key="", langsmith_tracing=False)
    rt = ObservabilityRuntime(settings=settings, export_traces=False, sleep_fn=lambda _s: None)
    slow_tool = rt.run(
        RunRequest(question="Where is ORD-1001?", scenario=FaultScenario.SLOW_TOOL)
    )
    slow_model = rt.run(
        RunRequest(question="Where is ORD-1001?", scenario=FaultScenario.SLOW_MODEL)
    )
    assert rt.find_bottleneck(slow_tool.trace_id)["bottleneck"] == "tool"
    assert rt.find_bottleneck(slow_model.trace_id)["bottleneck"] == "model"
