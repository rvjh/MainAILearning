from __future__ import annotations

from typing import Any


RUNBOOKS: dict[str, list[str]] = {
    "runbooks/slo_validated_latency.md": [
        "1. List recent jobs where validated_success=false or end_to_end_ms>60000.",
        "2. Open the slowest/failing trace; separate queue_wait vs execution.",
        "3. Check tool errors and model latency spans.",
        "4. If prompt/model version changed in the window, compare quality by version.",
        "5. Mitigate: roll back prompt_version or disable faulty tool; page only if burn continues.",
    ],
    "runbooks/job_failures.md": [
        "1. Group failures by error class (tool timeout, validation, permanent).",
        "2. Confirm retries exhausted vs first-attempt permanent failures.",
        "3. File ticket with sample job_ids and trace_ids.",
    ],
    "runbooks/stuck_jobs.md": [
        "1. Find jobs without heartbeat progress in last N minutes.",
        "2. Do not count them as successes in SLO reporting.",
        "3. Cancel or re-queue after worker health check.",
    ],
    "runbooks/queue_age.md": [
        "1. Prefer queue age over queue depth for user pain.",
        "2. Scale workers or pause intake if age keeps rising.",
    ],
    "runbooks/slow_runs.md": [
        "1. Identify bottleneck span (tool vs model).",
        "2. Inject known-good traffic to confirm systemic vs single tenant.",
    ],
}


def follow_runbook(path: str, *, alert: dict[str, Any] | None = None) -> dict[str, Any]:
    steps = RUNBOOKS.get(path, ["No runbook found — escalate to on-call."])
    return {
        "runbook": path,
        "alert": alert or {},
        "steps": steps,
        "owner": "support-ops-oncall",
    }
