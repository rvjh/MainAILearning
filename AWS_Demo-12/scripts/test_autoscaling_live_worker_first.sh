#!/usr/bin/env bash
# Worker QueueDepth scale-out, cooldown, then API load scale-out.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

"${SCRIPT_DIR}/reset_autoscaling_baseline.sh"

PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"
METRIC_NAMESPACE="${PROJECT_NAME}/Celery"
POLL_INTERVAL="${POLL_INTERVAL:-15}"
POLL_MAX="${POLL_MAX:-24}"
WORKER_PHASE_COOLDOWN="${WORKER_PHASE_COOLDOWN:-120}"
API_MAX_CAPACITY="${API_MAX_CAPACITY:-4}"
ROOT_PROOF="${PROOF_DIR:-${SCRIPT_DIR}/../proof/autoscaling-live-worker-first-$(date +%Y%m%d-%H%M%S)}"
PROOF_DIR="${ROOT_PROOF}"
mkdir -p "${PROOF_DIR}"

get_counts() {
  aws ecs describe-services --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" \
    --services "${API_SERVICE_NAME}" "${WORKER_SERVICE_NAME}" \
    --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount,pending:pendingCount}' \
    --output json
}

wait_for_scale() {
  local service_name="$1"
  local min_desired="$2"
  local label="$3"
  local i=0
  while [[ "${i}" -lt "${POLL_MAX}" ]]; do
    local desired
    desired="$(aws ecs describe-services --region "${AWS_REGION}" \
      --cluster "${CLUSTER_NAME}" --services "${service_name}" \
      --query 'services[0].desiredCount' --output text)"
    echo "  [${label}] poll $((i + 1))/${POLL_MAX}: desired=${desired} (need >= ${min_desired})"
    if [[ "${desired}" -ge "${min_desired}" ]]; then
      return 0
    fi
    sleep "${POLL_INTERVAL}"
    i=$((i + 1))
  done
  return 1
}

wait_for_stable() {
  local service_name="$1"
  local label="$2"
  local i=0
  while [[ "${i}" -lt "${POLL_MAX}" ]]; do
    local desired running pending
    read -r desired running pending <<<"$(aws ecs describe-services --region "${AWS_REGION}" \
      --cluster "${CLUSTER_NAME}" --services "${service_name}" \
      --query 'services[0].[desiredCount,runningCount,pendingCount]' --output text)"
    echo "  [${label}] stable poll $((i + 1))/${POLL_MAX}: desired=${desired} running=${running} pending=${pending}"
    if [[ "${running}" -ge "${desired}" && "${pending}" -eq 0 ]]; then
      return 0
    fi
    sleep "${POLL_INTERVAL}"
    i=$((i + 1))
  done
  return 1
}

publish_queue_depth() {
  local value="$1"
  aws cloudwatch put-metric-data --region "${AWS_REGION}" \
    --namespace "${METRIC_NAMESPACE}" \
    --metric-data "MetricName=QueueDepth,Value=${value},Unit=Count"
}

echo "=== Autoscaling live test (worker-first) ===" | tee "${PROOF_DIR}/README.txt"
echo "Proof directory: ${PROOF_DIR}" | tee -a "${PROOF_DIR}/README.txt"
echo "Order: worker scale-out -> cooldown -> API scale-out" | tee -a "${PROOF_DIR}/README.txt"
echo "" | tee -a "${PROOF_DIR}/README.txt"

echo "=== Policies (must exist) ===" | tee "${PROOF_DIR}/00-policies.txt"
if ! aws application-autoscaling describe-scaling-policies --region "${AWS_REGION}" \
  --service-namespace ecs \
  --query "ScalingPolicies[?contains(ResourceId, '${CLUSTER_NAME}')]" \
  --output table | tee -a "${PROOF_DIR}/00-policies.txt"; then
  echo "No ECS scaling policies found. Run ./scripts/configure_autoscaling.sh first." >&2
  exit 1
fi

policy_count="$(aws application-autoscaling describe-scaling-policies --region "${AWS_REGION}" \
  --service-namespace ecs \
  --query "length(ScalingPolicies[?contains(ResourceId, \`${CLUSTER_NAME}\`)])" \
  --output text)"
if [[ "${policy_count}" -lt 2 ]]; then
  echo "Expected API + worker scaling policies; found ${policy_count}. Run configure_autoscaling.sh." >&2
  exit 1
fi

echo "" | tee -a "${PROOF_DIR}/README.txt"
echo "=== Baseline ECS counts ===" | tee "${PROOF_DIR}/01-baseline.json"
get_counts | tee "${PROOF_DIR}/01-baseline.json"

baseline_api="$(aws ecs describe-services --region "${AWS_REGION}" --cluster "${CLUSTER_NAME}" \
  --services "${API_SERVICE_NAME}" --query 'services[0].desiredCount' --output text)"
baseline_worker="$(aws ecs describe-services --region "${AWS_REGION}" --cluster "${CLUSTER_NAME}" \
  --services "${WORKER_SERVICE_NAME}" --query 'services[0].desiredCount' --output text)"

echo "" | tee -a "${PROOF_DIR}/README.txt"
echo "=== Phase 1/2: Worker scale-out (QueueDepth custom metric) ===" | tee "${PROOF_DIR}/02-worker-test.txt"
echo "Publishing QueueDepth=25 to ${METRIC_NAMESPACE} (target scale-out threshold is typically 5)..." \
  | tee -a "${PROOF_DIR}/02-worker-test.txt"
publish_queue_depth 25 | tee -a "${PROOF_DIR}/02-worker-test.txt"

(
  while true; do
    sleep 30
    publish_queue_depth 25 >/dev/null
  done
) &
metric_pid=$!

worker_target=$((baseline_worker + 1))
if wait_for_scale "${WORKER_SERVICE_NAME}" "${worker_target}" "worker"; then
  echo "PASS: Worker desired count increased to >= ${worker_target}" | tee -a "${PROOF_DIR}/02-worker-test.txt"
  worker_pass=1
else
  echo "FAIL: Worker did not scale within $((POLL_MAX * POLL_INTERVAL))s" | tee -a "${PROOF_DIR}/02-worker-test.txt"
  worker_pass=0
fi
kill "${metric_pid}" 2>/dev/null || true
wait "${metric_pid}" 2>/dev/null || true

if wait_for_stable "${WORKER_SERVICE_NAME}" "worker-stable"; then
  echo "Worker tasks stable at scaled count." | tee -a "${PROOF_DIR}/02-worker-test.txt"
else
  echo "WARN: Worker tasks not fully stable before phase 2." | tee -a "${PROOF_DIR}/02-worker-test.txt"
fi
get_counts | tee "${PROOF_DIR}/02-worker-after.json"

echo "" | tee -a "${PROOF_DIR}/README.txt"
echo "=== Reset worker signal before API phase ===" | tee "${PROOF_DIR}/02b-worker-reset.txt"
echo "Publishing QueueDepth=0 (worker scale-in will follow after cooldown)..." \
  | tee -a "${PROOF_DIR}/02b-worker-reset.txt"
publish_queue_depth 0 | tee -a "${PROOF_DIR}/02b-worker-reset.txt"
echo "Waiting ${WORKER_PHASE_COOLDOWN}s so worker/API scale signals do not overlap..." \
  | tee -a "${PROOF_DIR}/02b-worker-reset.txt"
sleep "${WORKER_PHASE_COOLDOWN}"
get_counts | tee "${PROOF_DIR}/02b-after-cooldown.json"

echo "" | tee -a "${PROOF_DIR}/README.txt"
echo "=== Phase 2/2: API scale-out (ALB requests + CPU via sustained load) ===" | tee "${ROOT_PROOF}/03-api-test.txt"
API_LOAD_SECONDS="${API_LOAD_SECONDS:-360}"
API_LOAD_WORKERS="${API_LOAD_WORKERS:-80}"
echo "Sustained load: ${API_LOAD_SECONDS}s, ${API_LOAD_WORKERS} workers, URL=${API_BASE_URL}" \
  | tee -a "${ROOT_PROOF}/03-api-test.txt"

python3 - "${API_BASE_URL}" "${API_LOAD_SECONDS}" "${API_LOAD_WORKERS}" \
  > "${ROOT_PROOF}/03-api-load-output.txt" 2>&1 <<'PY' &
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib import request

base, seconds, workers = sys.argv[1:4]
seconds = int(seconds)
workers = int(workers)
health = base.rstrip("/") + "/health"
jobs = base.rstrip("/") + "/jobs"
payload = json.dumps({"query": "api autoscale sustained load"}).encode()

def hit(url, data=None):
    try:
        req = request.Request(
            url,
            data=data,
            method="POST" if data else "GET",
            headers={"Content-Type": "application/json"} if data else {},
        )
        with request.urlopen(req, timeout=10) as resp:
            return resp.status
    except Exception:
        return 0

end = time.time() + seconds
n = 0
with ThreadPoolExecutor(max_workers=workers) as pool:
    while time.time() < end:
        futs = []
        for _ in range(workers):
            if n % 4:
                futs.append(pool.submit(hit, health))
            else:
                futs.append(pool.submit(hit, jobs, payload))
            n += 1
        for fut in futs:
            fut.result()
print(f"completed_requests={n}")
PY
load_pid=$!

api_target=$((baseline_api + 1))
if [[ "${api_target}" -gt "${API_MAX_CAPACITY}" ]]; then
  api_target="${API_MAX_CAPACITY}"
fi
api_pass=0
if [[ "${baseline_api}" -ge "${API_MAX_CAPACITY}" ]]; then
  echo "SKIP: API already at max capacity (${API_MAX_CAPACITY})" | tee -a "${ROOT_PROOF}/03-api-test.txt"
  api_pass=1
elif wait_for_scale "${API_SERVICE_NAME}" "${api_target}" "api"; then
  echo "PASS: API desired count increased to >= ${api_target}" | tee -a "${ROOT_PROOF}/03-api-test.txt"
  api_pass=1
else
  echo "WARN: API did not scale within $((POLL_MAX * POLL_INTERVAL))s; checking after load completes..." \
    | tee -a "${ROOT_PROOF}/03-api-test.txt"
fi
wait "${load_pid}" 2>/dev/null || true
if [[ "${api_pass}" -eq 0 ]]; then
  desired="$(aws ecs describe-services --region "${AWS_REGION}" --cluster "${CLUSTER_NAME}" \
    --services "${API_SERVICE_NAME}" --query 'services[0].desiredCount' --output text)"
  if [[ "${desired}" -ge "${api_target}" ]]; then
    echo "PASS: API desired count reached ${desired} after sustained load" | tee -a "${ROOT_PROOF}/03-api-test.txt"
    api_pass=1
  else
    echo "FAIL: API desired count still ${desired} (need >= ${api_target})" | tee -a "${ROOT_PROOF}/03-api-test.txt"
  fi
fi
get_counts | tee "${ROOT_PROOF}/03-api-after.json"

echo "" | tee "${ROOT_PROOF}/SUMMARY.txt"
{
  echo "Autoscaling live test summary (worker-first) — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Phase 1 — Worker scale-out (QueueDepth metric): $([[ ${worker_pass:-0} -eq 1 ]] && echo PASS || echo FAIL)"
  echo "Phase 2 — API scale-out (load test):          $([[ ${api_pass:-0} -eq 1 ]] && echo PASS || echo FAIL)"
  echo "Worker phase cooldown: ${WORKER_PHASE_COOLDOWN}s"
  echo "Artifacts: ${ROOT_PROOF}"
} | tee "${ROOT_PROOF}/SUMMARY.txt"

if [[ "${worker_pass:-0}" -eq 1 && "${api_pass:-0}" -eq 1 ]]; then
  exit 0
fi
exit 1
