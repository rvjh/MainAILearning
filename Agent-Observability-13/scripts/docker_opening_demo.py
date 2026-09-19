#!/usr/bin/env python3
"""Docker path demo: two jobs through real API → Redis/Celery → observability agent.

Prereq:
  cd Session-Observability
  docker compose up --build
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

BASE = "http://localhost:8000"
TENANT = "tenant_acme"
USER = "user_42"


def headers(idem: str) -> dict[str, str]:
    return {
        "X-Demo-Tenant": TENANT,
        "X-Demo-User": USER,
        "Content-Type": "application/json",
        "Idempotency-Key": idem,
        "X-Request-ID": f"req-{uuid.uuid4().hex[:8]}",
    }


def wait_ready(client: httpx.Client, timeout: float = 120.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            live = client.get(f"{BASE}/health/live")
            ready = client.get(f"{BASE}/health/ready")
            if live.status_code == 200 and ready.status_code == 200:
                print("health live/ready: OK")
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit("API not ready. Run: docker compose up --build")


def wait_terminal(client: httpx.Client, job_id: str, timeout: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(
            f"{BASE}/v1/agent-jobs/{job_id}",
            headers={"X-Demo-Tenant": TENANT, "X-Demo-User": USER},
        ).json()
        if body["status"] in {"succeeded", "failed", "cancelled", "dead_lettered"}:
            return body
        time.sleep(1)
    raise TimeoutError(f"job {job_id} did not finish")


def submit(client: httpx.Client, *, scenario: str, prompt: str) -> dict[str, Any]:
    idem = f"obs-{scenario}-{uuid.uuid4().hex[:8]}"
    payload = {
        "prompt": prompt,
        "thread_id": f"thread-{scenario}",
        "max_attempts": 3,
        "metadata": {
            "pipeline": "observability",
            "obs_scenario": scenario,
        },
    }
    created = client.post(
        f"{BASE}/v1/agent-jobs",
        headers=headers(idem),
        json=payload,
    )
    created.raise_for_status()
    body = created.json()
    print(f"\n=== scenario={scenario} ===")
    print(f"accepted job_id={body['job_id']} status={body['status']}")
    final = wait_terminal(client, body["job_id"])
    result = final.get("result") or {}
    print(f"final status={final['status']}")
    print(f"answer={result.get('answer')}")
    print(
        json.dumps(
            {
                "pipeline": result.get("pipeline"),
                "scenario": result.get("scenario"),
                "grounded": result.get("grounded"),
                "business_success": result.get("business_success"),
                "budget_ok": result.get("budget_ok"),
                "provider": result.get("provider"),
            },
            indent=2,
        )
    )
    return final


def main() -> int:
    print("Docker observability path — real queue/worker")
    print(f"API: {BASE}")
    with httpx.Client(timeout=60.0) as client:
        wait_ready(client)
        good = submit(
            client,
            scenario="correct",
            prompt="What is the status of order ORD-1001?",
        )
        bad = submit(
            client,
            scenario="confidently_wrong",
            prompt="What is the status of order ORD-1001?",
        )
        good_ok = (good.get("result") or {}).get("business_success") is True
        bad_ok = (bad.get("result") or {}).get("business_success") is False
        assert good["status"] == "succeeded" and bad["status"] == "succeeded"
        assert good_ok and bad_ok
        print("\nDocker opening contrast: OK")
        print("Both jobs completed via Celery; only quality/business_success separates them.")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
