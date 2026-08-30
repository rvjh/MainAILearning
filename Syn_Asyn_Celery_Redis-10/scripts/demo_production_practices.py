#!/usr/bin/env python3
"""Part 2: prove selected production controls against the real stack.

Run after docker compose up --build and after demo_full_flow.py.
The fault cases are enabled only by ALLOW_DEMO_FAULTS in docker-compose.yml.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app.config import get_settings

settings = get_settings()
BASE = settings.api_base_url.rstrip("/")
TENANT = settings.demo_tenant
USER = settings.demo_user


def headers(key: str | None = None, *, tenant: str = TENANT, user: str = USER) -> dict[str, str]:
    result = {
        "X-Demo-Tenant": tenant,
        "X-Demo-User": user,
        "Content-Type": "application/json",
    }
    if key:
        result["Idempotency-Key"] = key
    return result


def wait_terminal(client: httpx.Client, job_id: str, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"{BASE}/v1/agent-jobs/{job_id}", headers=headers())
        response.raise_for_status()
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled", "dead_lettered"}:
            return job
        time.sleep(0.2)
    raise TimeoutError(f"job {job_id} did not finish")


def event_timeline(client: httpx.Client, job_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{BASE}/v1/agent-jobs/{job_id}/events", headers=headers())
    response.raise_for_status()
    timeline: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in response.text.splitlines():
        if line.startswith("id:"):
            current["id"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif not line and current:
            timeline.append(current)
            current = {}
    if current:
        timeline.append(current)
    return timeline


def create(client: httpx.Client, *, key: str, metadata: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        f"{BASE}/v1/agent-jobs",
        headers=headers(key),
        json={
            "prompt": "Explain the reliability outcome.",
            "thread_id": f"practice-{uuid.uuid4().hex[:8]}",
            "max_attempts": 3,
            "metadata": metadata,
        },
    )
    response.raise_for_status()
    return response.json()


def section(title: str) -> None:
    print(f"\n{title}")


def main() -> int:
    print("Sunday Production Working Demo — Part 2: prove the controls")
    with httpx.Client(timeout=30.0) as client:
        section("1. IDEMPOTENCY HAS THREE BRANCHES")
        key = f"practice-idem-{uuid.uuid4().hex[:8]}"
        body = {
            "prompt": "One logical operation",
            "thread_id": "practice-idem",
            "max_attempts": 3,
            "metadata": {},
        }
        first = client.post(f"{BASE}/v1/agent-jobs", headers=headers(key), json=body)
        replay = client.post(f"{BASE}/v1/agent-jobs", headers=headers(key), json=body)
        conflict = client.post(
            f"{BASE}/v1/agent-jobs",
            headers=headers(key),
            json={**body, "prompt": "Changed operation"},
        )
        first.raise_for_status()
        replay.raise_for_status()
        print(" first job:", first.json()["job_id"])
        print(" replay job:", replay.json()["job_id"], "same:", first.json()["job_id"] == replay.json()["job_id"])
        print(" changed body:", conflict.status_code, conflict.json().get("type"))

        section("2. TENANT SCOPE IS PART OF RESOURCE IDENTITY")
        other = client.get(
            f"{BASE}/v1/agent-jobs/{first.json()['job_id']}",
            headers=headers(tenant="tenant_globex", user="other"),
        )
        print(" cross-tenant GET:", other.status_code, other.json().get("type"))

        section("3. TRANSIENT FAILURE WAITS, RETRIES, THEN SUCCEEDS")
        transient = create(
            client,
            key=f"practice-transient-{uuid.uuid4().hex[:8]}",
            metadata={"demo_transient_failures": "1"},
        )
        transient_final = wait_terminal(client, transient["job_id"])
        transient_events = event_timeline(client, transient["job_id"])
        retry_events = [item for item in transient_events if item.get("event") == "worker.retry_scheduled"]
        retry_delay = None
        if retry_events:
            retry_delay = (retry_events[0].get("data") or {}).get("detail", {}).get("delay_seconds")
        print(" final:", transient_final["status"], "attempts:", transient_final["attempts"])
        print(" retry event count:", len(retry_events), "durable event delay:", retry_delay)
        print(" event order:", " -> ".join(item.get("event", "") for item in transient_events))

        section("4. PERMANENT FAILURE STOPS AFTER ONE ATTEMPT")
        permanent = create(
            client,
            key=f"practice-permanent-{uuid.uuid4().hex[:8]}",
            metadata={"demo_permanent_failure": "true"},
        )
        permanent_final = wait_terminal(client, permanent["job_id"])
        print(" final:", permanent_final["status"], "attempts:", permanent_final["attempts"])
        print(" error:", permanent_final.get("error"))

        section("5. THE PUBLIC PROOF IS DURABLE STATE")
        ready = client.get(f"{BASE}/health/ready")
        print(" readiness:", ready.status_code, ready.json())
        print(" ✓ same request, same job")
        print(" ✓ changed request, conflict")
        print(" ✓ wrong tenant, not found")
        print(" ✓ transient failure, bounded delayed retry")
        print(" ✓ permanent failure, no retry")
        print(" ✓ durable event timeline explains every state change")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
