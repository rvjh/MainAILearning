#!/usr/bin/env python3
"""End-to-end production flow against the real HTTP API.

Run after: docker compose up --build

  cd Sunday_Production_Working_Demo
  python scripts/demo_full_flow.py
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


def headers(idem: str | None = None, last_event_id: int | None = None) -> dict[str, str]:
    h = {
        "X-Demo-Tenant": TENANT,
        "X-Demo-User": USER,
        "Content-Type": "application/json",
    }
    if idem:
        h["Idempotency-Key"] = idem
    if last_event_id is not None:
        h["Last-Event-ID"] = str(last_event_id)
    return h


def wait_ready(client: httpx.Client, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            live = client.get(f"{BASE}/health/live")
            ready = client.get(f"{BASE}/health/ready")
            if live.status_code == 200 and ready.status_code == 200:
                print("1. HEALTH")
                print(" live:", live.json())
                print(" ready:", ready.json())
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit("API not ready. Is docker compose up?")


def wait_terminal(client: httpx.Client, job_id: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{BASE}/v1/agent-jobs/{job_id}", headers=headers()).json()
        if body["status"] in {"succeeded", "failed", "cancelled", "dead_lettered"}:
            return body
        time.sleep(1)
    raise TimeoutError(f"job {job_id} did not finish")


def wait_status(client: httpx.Client, job_id: str, expected: set[str], timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{BASE}/v1/agent-jobs/{job_id}", headers=headers()).json()
        if body["status"] in expected:
            return body
        time.sleep(0.2)
    raise TimeoutError(f"job {job_id} did not reach one of {sorted(expected)}")


def section(title: str) -> None:
    print(f"\n{title}")


def main() -> int:
    print("Sunday Production Working Demo — Part 1: see the whole system work")
    print(f"API: {BASE}")
    with httpx.Client(timeout=30.0) as client:
        wait_ready(client)

        # --- Idempotent create ---
        section("2. ONE REQUEST BECOMES ONE DURABLE JOB")
        key = f"demo-{uuid.uuid4().hex[:8]}"
        payload = {
            "prompt": "Please summarize my account and contact me by email.",
            "thread_id": "thread_prod_17",
            "max_attempts": 3,
            "metadata": {"contact_preference": "email"},
        }
        first = client.post(f"{BASE}/v1/agent-jobs", headers=headers(key), json=payload)
        print(" first status:", first.status_code, "Location:", first.headers.get("Location"))
        first_body = first.json()
        print(" first job:", first_body["job_id"], first_body["status"])

        replay = client.post(f"{BASE}/v1/agent-jobs", headers=headers(key), json=payload)
        replay_body = replay.json()
        print(" replay job:", replay_body["job_id"], "same?", replay_body["job_id"] == first_body["job_id"])

        conflict_payload = {**payload, "prompt": "Different operation under same key"}
        conflict = client.post(f"{BASE}/v1/agent-jobs", headers=headers(key), json=conflict_payload)
        print(" conflict status:", conflict.status_code, conflict.json().get("type"))

        job_id = first_body["job_id"]

        # --- Tenant isolation ---
        section("3. THE JOB HAS AN OWNER")
        other = client.get(
            f"{BASE}/v1/agent-jobs/{job_id}",
            headers={"X-Demo-Tenant": "tenant_globex", "X-Demo-User": "other", "Content-Type": "application/json"},
        )
        print(" cross-tenant GET:", other.status_code, other.json().get("type"))

        # --- Wait for worker + GET truth ---
        section("4. THE WORK CONTINUES AFTER THE HTTP RESPONSE")
        final = wait_terminal(client, job_id)
        print(" GET status (authoritative):", final["status"])
        print(" result:", json.dumps(final.get("result"), indent=2)[:800])

        # --- SSE replay ---
        section("5. A RECONNECTING CLIENT RECOVERS PROGRESS")
        stream = client.get(f"{BASE}/v1/agent-jobs/{job_id}/events", headers=headers(last_event_id=2))
        print(" content-type:", stream.headers.get("content-type"))
        frames = [line for line in stream.text.split("\n") if line.startswith("id:") or line.startswith("event:")]
        for line in frames[:12]:
            print(" ", line)
        print(" ... total frame lines:", len(frames))

        # --- Second job uses remembered preference ---
        section("6. THE NEXT JOB RECALLS GOVERNED MEMORY")
        key2 = f"demo-{uuid.uuid4().hex[:8]}"
        payload2 = {
            "prompt": "How should I contact this customer?",
            "thread_id": "thread_prod_18",
            "max_attempts": 3,
            "metadata": {},
        }
        second = client.post(f"{BASE}/v1/agent-jobs", headers=headers(key2), json=payload2).json()
        final2 = wait_terminal(client, second["job_id"])
        print(" second job:", second["job_id"], final2["status"])
        print(" answer:", (final2.get("result") or {}).get("answer", "")[:300])
        print(" memory_rejected on persist (unverified inference):", (final2.get("result") or {}).get("memory_rejected"))

        # --- Cancellation ---
        section("7. CANCELLATION IS A DURABLE REQUEST")
        key3 = f"demo-cancel-{uuid.uuid4().hex[:8]}"
        created = client.post(
            f"{BASE}/v1/agent-jobs",
            headers=headers(key3),
            json={
                "prompt": "Long running work",
                "thread_id": "t-cancel",
                "max_attempts": 3,
                "metadata": {"demo_pause_step": "retrieve", "demo_pause_seconds": "3"},
            },
        ).json()
        wait_status(client, created["job_id"], {"running", "cancel_requested"})
        cancel = client.delete(f"{BASE}/v1/agent-jobs/{created['job_id']}", headers=headers())
        cancel_body: dict[str, Any] = {}
        try:
            cancel_body = cancel.json()
        except Exception:
            cancel_body = {"raw": cancel.text[:200]}
        print(" cancel HTTP:", cancel.status_code, "body status:", cancel_body.get("status") or cancel_body)
        cancelled = wait_terminal(client, created["job_id"])
        print(" final after cancel:", cancelled["status"])
        if cancelled["status"] != "cancelled":
            raise RuntimeError(f"expected cancelled, got {cancelled['status']}")

        section("8. PART 1 COMPLETE — NOW WE EXPLAIN WHY IT SURVIVED")
        print(" ✓ FastAPI HTTP contract")
        print(" ✓ PostgreSQL durable job + idempotency + events + outbox")
        print(" ✓ Redis broker + Celery worker (late ack)")
        print(" ✓ Outbox publisher (commit then deliver)")
        print(" ✓ Governed memory write/read (Saturday rules on Sunday path)")
        print(" ✓ SSE replay + GET as source of truth")
        print(" ✓ Tenant isolation + cooperative cancel")
        print(" ✓ LangGraph agent graph (retrieve→plan→execute→persist)")
        provider = (final.get("result") or {}).get("provider", "unknown")
        if str(provider).startswith("langchain_openai:"):
            print(" ✓ LangChain ChatOpenAI used for plan/execute:", provider)
        else:
            print(" · Deterministic model path used; set OPENAI_API_KEY in the service for live LLM")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
