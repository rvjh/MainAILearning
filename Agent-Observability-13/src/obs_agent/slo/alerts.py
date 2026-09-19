from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlertEvent:
    name: str
    severity: str  # page | ticket
    message: str
    affected_job_ids: list[str] = field(default_factory=list)
    runbook: str = ""


def evaluate_alerts(
    *,
    runs: list[dict[str, Any]],
    slo_result: dict[str, Any],
    queue_age_ms_max: float = 0.0,
) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []
    failed = [r for r in runs if r.get("status") == "failed"]
    overdue = [r for r in runs if r.get("status") == "overdue" or r.get("unresolved")]
    slow = [r for r in runs if float(r.get("end_to_end_ms", 0)) > 60_000]

    if slo_result.get("breached") and slo_result.get("eligible", 0) >= 5:
        alerts.append(
            AlertEvent(
                name="slo_burn_validated_latency",
                severity="page",
                message=(
                    f"SLO breached: ratio={slo_result['ratio']:.3f} "
                    f"(target={0.99:.2f}) over {slo_result['eligible']} eligible jobs"
                ),
                affected_job_ids=[r["job_id"] for r in runs if not r.get("validated_success")][:10],
                runbook="runbooks/slo_validated_latency.md",
            )
        )

    if len(failed) >= 2:
        alerts.append(
            AlertEvent(
                name="sustained_job_failures",
                severity="ticket",
                message=f"{len(failed)} failed jobs in window",
                affected_job_ids=[r["job_id"] for r in failed],
                runbook="runbooks/job_failures.md",
            )
        )

    if overdue:
        alerts.append(
            AlertEvent(
                name="unresolved_or_overdue_jobs",
                severity="page",
                message=f"{len(overdue)} overdue/unresolved jobs still pending",
                affected_job_ids=[r["job_id"] for r in overdue],
                runbook="runbooks/stuck_jobs.md",
            )
        )

    if queue_age_ms_max > 30_000:
        alerts.append(
            AlertEvent(
                name="queue_age_high",
                severity="ticket",
                message=f"Max queue age {queue_age_ms_max:.0f}ms (threshold 30000ms)",
                affected_job_ids=[],
                runbook="runbooks/queue_age.md",
            )
        )

    if slow and not slo_result.get("breached"):
        alerts.append(
            AlertEvent(
                name="slow_validated_runs",
                severity="ticket",
                message=f"{len(slow)} runs exceeded 60s (investigation, not page)",
                affected_job_ids=[r["job_id"] for r in slow][:10],
                runbook="runbooks/slow_runs.md",
            )
        )

    return alerts
