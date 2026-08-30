#!/usr/bin/env python3
"""Chaos proofs against the live API (duplicate POST, conflict, readiness)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app.config import get_settings

settings = get_settings()
BASE = settings.api_base_url.rstrip("/")


def auth(tenant: str = settings.demo_tenant, user: str = settings.demo_user, key: str | None = None):
    h = {"X-Demo-Tenant": tenant, "X-Demo-User": user, "Content-Type": "application/json"}
    if key:
        h["Idempotency-Key"] = key
    return h


def main() -> None:
    with httpx.Client(timeout=30.0) as client:
        print("live", client.get(f"{BASE}/health/live").status_code)
        print("ready", client.get(f"{BASE}/health/ready").json())

        key = f"chaos-{uuid.uuid4().hex[:8]}"
        body = {"prompt": "chaos", "thread_id": "t1", "max_attempts": 2}
        a = client.post(f"{BASE}/v1/agent-jobs", headers=auth(key=key), json=body).json()
        b = client.post(f"{BASE}/v1/agent-jobs", headers=auth(key=key), json=body).json()
        print("duplicate POST same job?", a["job_id"] == b["job_id"])

        c = client.post(
            f"{BASE}/v1/agent-jobs",
            headers=auth(key=key),
            json={**body, "prompt": "changed"},
        )
        print("payload conflict", c.status_code, c.json().get("type"))

        other = client.get(
            f"{BASE}/v1/agent-jobs/{a['job_id']}",
            headers=auth(tenant="other_tenant", user="x"),
        )
        print("cross-tenant", other.status_code)


if __name__ == "__main__":
    main()
