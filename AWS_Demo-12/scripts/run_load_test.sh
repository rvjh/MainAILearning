#!/usr/bin/env bash
# Performance / rate-limit load test against /health and /jobs (classroom proof).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${LOAD_TEST_URL:-}" ]]; then
  if [[ -z "${AWS_REGION:-}" ]]; then
    echo "Set LOAD_TEST_URL or AWS_REGION (and deploy stack) so we can read the ALB URL." >&2
    echo "  export AWS_REGION=us-east-1" >&2
    echo "  source ./scripts/load_stack_outputs.sh && export LOAD_TEST_URL=\$API_BASE_URL" >&2
    echo "  ./scripts/run_load_test.sh" >&2
    exit 1
  fi
  # shellcheck source=load_stack_outputs.sh
  source "${SCRIPT_DIR}/load_stack_outputs.sh"
  LOAD_TEST_URL="${API_BASE_URL}"
fi
export LOAD_TEST_URL

CONCURRENCY="${CONCURRENCY:-20}"
REQUESTS="${REQUESTS:-60}"
PROOF_DIR="${PROOF_DIR:-${SCRIPT_DIR}/../proof/load-test-$(date +%Y%m%d-%H%M%S)}"

mkdir -p "${PROOF_DIR}"

echo "Load test: ${LOAD_TEST_URL}"
echo "  concurrency=${CONCURRENCY} total_requests=${REQUESTS}"
echo "  output=${PROOF_DIR}"

python3 - "${LOAD_TEST_URL}" "${CONCURRENCY}" "${REQUESTS}" "${PROOF_DIR}" <<'PY'
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import error, request

base, concurrency, total, proof_dir = sys.argv[1:5]
concurrency = int(concurrency)
total = int(total)

health_url = base.rstrip("/") + "/health"
jobs_url = base.rstrip("/") + "/jobs"
payload = json.dumps({"query": "load test autoscaling proof"}).encode()


def hit_health(_):
    start = time.perf_counter()
    try:
        req = request.Request(health_url)
        with request.urlopen(req, timeout=10) as resp:
            return resp.status, time.perf_counter() - start, None
    except error.HTTPError as exc:
        return exc.code, time.perf_counter() - start, None
    except Exception as exc:
        return 0, time.perf_counter() - start, str(exc)


def hit_jobs(_):
    start = time.perf_counter()
    try:
        req = request.Request(
            jobs_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=15) as resp:
            return resp.status, time.perf_counter() - start, None
    except error.HTTPError as exc:
        return exc.code, time.perf_counter() - start, None
    except Exception as exc:
        return 0, time.perf_counter() - start, str(exc)


results = {"health": [], "jobs": []}
started = time.perf_counter()

with ThreadPoolExecutor(max_workers=concurrency) as pool:
    futures = []
    for i in range(total):
        futures.append(pool.submit(hit_health if i % 3 else hit_jobs, i))
    for fut in as_completed(futures):
        kind = "health" if fut in futures[:1] else "jobs"  # noqa: simplified tracking
        # Re-run with explicit kind tracking below

# clearer run
results = {"health": [], "jobs": []}
with ThreadPoolExecutor(max_workers=concurrency) as pool:
    health_futs = [pool.submit(hit_health, i) for i in range(total)]
    for fut in as_completed(health_futs):
        status, elapsed, err = fut.result()
        results["health"].append({"status": status, "latency_s": round(elapsed, 4), "error": err})

    job_futs = [pool.submit(hit_jobs, i) for i in range(max(10, total // 3))]
    for fut in as_completed(job_futs):
        status, elapsed, err = fut.result()
        results["jobs"].append({"status": status, "latency_s": round(elapsed, 4), "error": err})

elapsed = time.perf_counter() - started


def summarize(rows):
    statuses = {}
    latencies = []
    for row in rows:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
        if row["latency_s"]:
            latencies.append(row["latency_s"])
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    return {"count": len(rows), "statuses": statuses, "p50_s": p50, "p95_s": p95}


summary = {
    "url": base,
    "concurrency": concurrency,
    "duration_s": round(elapsed, 2),
    "health": summarize(results["health"]),
    "jobs": summarize(results["jobs"]),
}
out = f"{proof_dir}/load-test-summary.json"
with open(out, "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2)
print(json.dumps(summary, indent=2))
print(f"Wrote {out}")
PY

echo "Check ECS desired count and CloudWatch metrics after load:"
echo "  ./scripts/prove_autoscaling.sh"
