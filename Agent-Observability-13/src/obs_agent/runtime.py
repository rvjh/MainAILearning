"""Async-style job runtime: accept → queue → worker → validate → metrics."""

from __future__ import annotations

import time
from typing import Any, Callable

from obs_agent.agent import SupportOpsAgent
from obs_agent.config import Settings, get_settings
from obs_agent.contracts import (
    FaultScenario,
    HealthScorecard,
    JobStatus,
    RunRequest,
    RunResult,
    ToolCallRecord,
)
from obs_agent.cost import check_budgets, estimate_chat_cost_usd
from obs_agent.quality import check_business_outcome, evaluate_answer, validate_output
from obs_agent.quality.online import maybe_record_feedback
from obs_agent.slo import ClassroomSLO, evaluate_alerts, follow_runbook
from obs_agent.telemetry import MetricsRegistry, TelemetryStore, start_trace
from obs_agent.telemetry.redact import redact_payload
from obs_agent.telemetry.spans import new_id


class ObservabilityRuntime:
    """Enterprise-shaped classroom runtime without requiring Docker."""

    PERF_BUDGET_MS = 2000.0
    QUEUE_DEMO_MS = {
        FaultScenario.SLOW_TOOL: 40.0,
        FaultScenario.SLOW_MODEL: 40.0,
        FaultScenario.STUCK_HEARTBEAT: 80.0,
    }

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        agent: SupportOpsAgent | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        export_traces: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.sleep = sleep_fn or time.sleep
        self.agent = agent or SupportOpsAgent(settings=self.settings, sleep_fn=self.sleep)
        self.metrics = MetricsRegistry()
        export_path = self.settings.logs_dir / "traces.jsonl" if export_traces else None
        if export_path:
            self.settings.logs_dir.mkdir(parents=True, exist_ok=True)
        self.store = TelemetryStore(export_path=export_path)
        self.runs: list[RunResult] = []
        self.online_events: list[dict[str, Any]] = []
        self.slo = ClassroomSLO()

    def run(self, request: RunRequest) -> RunResult:
        request_id = new_id("req")
        job_id = new_id("job")
        attempt_id = new_id("attempt")
        versions = {
            "agent_version": self.settings.agent_version,
            "prompt_version": self.settings.prompt_version,
            "deployment_version": self.settings.deployment_version,
            "model": self.settings.openai_model if self.settings.use_llm else "deterministic",
        }

        self.metrics.incr("jobs_accepted", labels={"agent_version": versions["agent_version"]})
        ctx = start_trace(job_id=job_id, request_id=request_id, attempt_id=attempt_id)
        t0 = time.perf_counter()

        with ctx.span(
            "support_ops.job",
            kind="server",
            attributes={
                "job.id": job_id,
                "request.id": request_id,
                "attempt.id": attempt_id,
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "support-ops",
                "agent.version": versions["agent_version"],
                "prompt.version": versions["prompt_version"],
                "deployment.version": versions["deployment_version"],
                "fault.scenario": request.scenario.value,
            },
        ) as root:
            # --- queue wait (async boundary) ---
            queue_ms = self.QUEUE_DEMO_MS.get(request.scenario, 15.0)
            with ctx.span(
                "support_ops.queue_wait",
                attributes={"queue.name": "support-ops", "job.status": JobStatus.QUEUED.value},
            ):
                self.sleep(queue_ms / 1000.0)
            self.metrics.observe("latency_queue_wait_ms", queue_ms)

            if request.scenario == FaultScenario.STUCK_HEARTBEAT:
                # Persist progress signal then stop — stuck work must remain visible.
                with ctx.span("support_ops.heartbeat", attributes={"progress": "retrieve_started"}):
                    pass
                result = RunResult(
                    job_id=job_id,
                    request_id=request_id,
                    attempt_id=attempt_id,
                    trace_id=ctx.trace_id,
                    status=JobStatus.OVERDUE,
                    answer="",
                    queue_wait_ms=queue_ms,
                    execution_ms=0.0,
                    end_to_end_ms=(time.perf_counter() - t0) * 1000,
                    versions=versions,
                    errors=["stuck_no_heartbeat"],
                    business_success=False,
                    health=HealthScorecard(
                        reliability=False,
                        performance=False,
                        quality=False,
                        efficiency=True,
                        safety=True,
                        notes={"reliability": "overdue_without_completion"},
                    ),
                )
                root.attributes["job.status"] = result.status.value
                self._finalize(ctx, result, extras={"heartbeat": "stale"})
                return result

            exec_started = time.perf_counter()
            with ctx.span("support_ops.worker", attributes={"worker.id": "local-1"}):
                with ctx.span("gen_ai.agent.retrieve"):
                    pass  # filled by agent steps; timing captured around invoke
                agent_out = self.agent.invoke(
                    question=request.question,
                    scenario=request.scenario,
                    order_id=request.order_id,
                    tenant_id=request.tenant_id,
                )

            # Attach detailed child spans from agent step timings (synthetic but labeled).
            tool_calls = [ToolCallRecord.model_validate(tc) for tc in agent_out.get("tool_calls") or []]
            for tc in tool_calls:
                with ctx.span(
                    "gen_ai.tool.call",
                    kind="client",
                    attributes={
                        "gen_ai.tool.name": tc.name,
                        "tool.ok": tc.ok,
                        "tool.denied": tc.denied,
                        "tool.attempt": tc.attempt,
                        "tool.latency_ms": tc.latency_ms,
                    },
                ) as tool_span:
                    # Preserve measured tool latency for bottleneck labs (sleep already done).
                    tool_span.duration_ms = tc.latency_ms
                    self.metrics.incr("tool_calls", labels={"tool": tc.name})
                    if not tc.ok and not tc.denied:
                        if "timeout" in tc.output:
                            self.metrics.incr("tool_timeouts", labels={"tool": tc.name})
                        else:
                            self.metrics.incr("tool_errors", labels={"tool": tc.name})
                    if tc.denied:
                        self.metrics.incr("tool_denials", labels={"tool": tc.name})

            model_latency = float(agent_out.get("model_latency_ms") or 0.0)
            with ctx.span(
                "gen_ai.client.inference",
                kind="client",
                attributes={
                    "gen_ai.request.model": versions["model"],
                    "gen_ai.usage.input_tokens": agent_out.get("prompt_tokens", 0),
                    "gen_ai.usage.output_tokens": agent_out.get("completion_tokens", 0),
                    "model.latency_ms": model_latency,
                },
            ) as model_span:
                model_span.duration_ms = model_latency
                self.metrics.observe("latency_model_ms", model_latency)

            answer = str(agent_out.get("answer") or "")
            citations = list(agent_out.get("citations") or [])
            evidence = list(agent_out.get("evidence") or [])
            steps = list(agent_out.get("steps") or [])
            prompt_tokens = int(agent_out.get("prompt_tokens") or 0)
            completion_tokens = int(agent_out.get("completion_tokens") or 0)
            cost = estimate_chat_cost_usd(prompt_tokens, completion_tokens)

            with ctx.span("support_ops.validate"):
                validation = validate_output(
                    answer=answer,
                    citations=citations,
                    tool_calls=tool_calls,
                    require_citation=True,
                )
                grounded_ok, ground_failures, _note = evaluate_answer(
                    answer=answer, evidence=evidence
                )
                business_ok = check_business_outcome(
                    question=request.question,
                    answer=answer,
                    tool_calls=tool_calls,
                    grounded=grounded_ok,
                    validation_ok=validation.ok,
                )

            execution_ms = (time.perf_counter() - exec_started) * 1000
            end_to_end_ms = (time.perf_counter() - t0) * 1000
            budget_ok, budget_failures = check_budgets(
                step_count=len(steps),
                tool_call_count=len(tool_calls),
                estimated_cost_usd=cost,
                execution_ms=execution_ms,
                max_tool_calls=4 if request.scenario != FaultScenario.BUDGET_BREACH_SUCCESS else 3,
                max_cost_usd=(
                    0.0005
                    if request.scenario == FaultScenario.OVERSIZED_CONTEXT
                    else 0.02
                ),
            )

            denied = any(tc.denied for tc in tool_calls)
            health = HealthScorecard(
                reliability=True,  # completed path
                performance=end_to_end_ms <= self.PERF_BUDGET_MS,
                quality=bool(validation.ok and grounded_ok and business_ok),
                efficiency=budget_ok,
                safety=not denied or request.scenario == FaultScenario.DENIED_TOOL,
                notes={
                    "quality": ",".join(validation.failures + ground_failures) or "ok",
                    "efficiency": ",".join(budget_failures) or "ok",
                    "safety": "denied_tool_observed" if denied else "ok",
                    "performance": f"e2e_ms={end_to_end_ms:.0f}",
                },
            )
            # Safety: denied tool is a successful policy enforcement for DENIED_TOOL demo.
            if request.scenario == FaultScenario.DENIED_TOOL:
                health.safety = True
                health.notes["safety"] = "policy_enforced"
                health.quality = False
                health.notes["quality"] = "business_task_incomplete"

            status = JobStatus.COMPLETED
            root.attributes["job.status"] = status.value

            result = RunResult(
                job_id=job_id,
                request_id=request_id,
                attempt_id=attempt_id,
                trace_id=ctx.trace_id,
                status=status,
                answer=answer,
                citations=citations,
                tool_calls=tool_calls,
                steps=steps,
                queue_wait_ms=queue_ms,
                execution_ms=execution_ms,
                end_to_end_ms=end_to_end_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=cost,
                validation=validation,
                grounded=grounded_ok,
                business_success=business_ok,
                health=health,
                versions=versions,
                errors=list(agent_out.get("errors") or []),
                budget_ok=budget_ok,
                budget_failures=budget_failures,
            )

            # Online eval sampling
            event = maybe_record_feedback(
                trace_id=ctx.trace_id,
                question=request.question,
                answer=answer,
                rate=1.0 if not grounded_ok else 0.25,
                auto_labels={
                    "grounded": grounded_ok,
                    "scenario": request.scenario.value,
                    "agent_version": versions["agent_version"],
                },
            )
            if event:
                self.online_events.append(event.model_dump())

            self._finalize(ctx, result)
            return result

    def _finalize(self, ctx: Any, result: RunResult, *, extras: dict[str, Any] | None = None) -> None:
        labels = {"agent_version": result.versions.get("agent_version", "unknown")}
        if result.status == JobStatus.COMPLETED:
            self.metrics.incr("jobs_completed", labels=labels)
        elif result.status == JobStatus.FAILED:
            self.metrics.incr("jobs_failed", labels=labels)
        elif result.status == JobStatus.OVERDUE:
            self.metrics.incr("jobs_overdue", labels=labels)
        elif result.status == JobStatus.CANCELLED:
            self.metrics.incr("jobs_cancelled", labels=labels)

        self.metrics.observe("latency_end_to_end_ms", result.end_to_end_ms)
        self.metrics.observe("latency_execution_ms", result.execution_ms)
        self.metrics.incr("tokens_in", float(result.prompt_tokens))
        self.metrics.incr("tokens_out", float(result.completion_tokens))
        self.metrics.incr("estimated_cost_usd", result.estimated_cost_usd)

        if result.validation and result.validation.ok and result.grounded and result.business_success:
            self.metrics.incr("validated_success", labels=labels)
        else:
            self.metrics.incr("validated_failure", labels=labels)

        sampled = len(self.online_events)
        total = max(1, len(self.runs) + 1)
        self.metrics.set_gauge("eval_coverage", sampled / total)

        export = redact_payload(
            {
                "job_id": result.job_id,
                "trace_id": result.trace_id,
                "status": result.status.value,
                "question": "see_policy",  # avoid raw by default in attributes
                "answer": result.answer,
                "scenario_health": result.health.model_dump() if result.health else {},
                **(extras or {}),
            },
            capture_full_prompts=False,
        )
        self.store.record_trace(
            ctx,
            extras={
                "result": result.model_dump(),
                "redacted": export,
            },
        )
        self.runs.append(result)

    def dashboard(self) -> dict[str, Any]:
        view = self.metrics.dashboard_view()
        view["recent_runs"] = [
            {
                "job_id": r.job_id,
                "trace_id": r.trace_id,
                "status": r.status.value,
                "business_success": r.business_success,
                "grounded": r.grounded,
                "end_to_end_ms": r.end_to_end_ms,
                "queue_wait_ms": r.queue_wait_ms,
                "execution_ms": r.execution_ms,
                "cost_usd": r.estimated_cost_usd,
                "agent_version": r.versions.get("agent_version"),
                "health": r.health.model_dump() if r.health else None,
            }
            for r in self.runs[-20:]
        ]
        view["online_eval_events"] = len(self.online_events)
        return view

    def slo_report(self) -> dict[str, Any]:
        rows = []
        for r in self.runs:
            rows.append(
                {
                    "job_id": r.job_id,
                    "eligible": True,
                    "cancelled": r.status == JobStatus.CANCELLED,
                    "unresolved": r.status == JobStatus.OVERDUE,
                    "validated_success": bool(
                        r.validation and r.validation.ok and r.grounded and r.business_success
                    ),
                    "end_to_end_ms": r.end_to_end_ms,
                    "status": r.status.value,
                }
            )
        slo_result = self.slo.evaluate(rows)
        queue_age = max((r.queue_wait_ms for r in self.runs), default=0.0)
        alerts = evaluate_alerts(runs=rows, slo_result=slo_result, queue_age_ms_max=queue_age)
        for alert in alerts:
            for r in self.runs:
                if r.job_id in alert.affected_job_ids:
                    r.alert_fired.append(alert.name)
        return {
            "slo": slo_result,
            "alerts": [
                {
                    "name": a.name,
                    "severity": a.severity,
                    "message": a.message,
                    "affected_job_ids": a.affected_job_ids,
                    "runbook": follow_runbook(a.runbook, alert={"name": a.name}),
                }
                for a in alerts
            ],
        }

    def find_bottleneck(self, trace_id: str) -> dict[str, Any]:
        for trace in self.store.traces:
            if trace["trace_id"] != trace_id:
                continue
            spans = trace.get("spans") or []
            named = {
                s["name"]: s.get("duration_ms") or 0.0
                for s in spans
                if s.get("duration_ms") is not None
            }
            # Prefer tool vs model comparison for the lab.
            def _span_ms(s: dict) -> float:
                attrs = s.get("attributes") or {}
                return float(
                    attrs.get("tool.latency_ms")
                    or attrs.get("model.latency_ms")
                    or s.get("duration_ms")
                    or 0.0
                )

            tool_total = sum(
                _span_ms(s) for s in spans if s.get("name") == "gen_ai.tool.call"
            )
            model_total = sum(
                _span_ms(s) for s in spans if s.get("name") == "gen_ai.client.inference"
            )
            queue = named.get("support_ops.queue_wait", 0.0)
            if tool_total >= model_total and tool_total >= queue:
                culprit = "tool"
                ms = tool_total
            elif model_total >= queue:
                culprit = "model"
                ms = model_total
            else:
                culprit = "queue"
                ms = queue
            return {
                "trace_id": trace_id,
                "bottleneck": culprit,
                "duration_ms": ms,
                "queue_ms": queue,
                "tool_ms": tool_total,
                "model_ms": model_total,
                "span_names": sorted(named.keys()),
            }
        return {"trace_id": trace_id, "bottleneck": "unknown"}
