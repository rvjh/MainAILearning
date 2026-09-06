#!/usr/bin/env bash
# Collect proof artifacts for autoscaling and rate limits (before/after load).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"
PROOF_DIR="${PROOF_DIR:-${SCRIPT_DIR}/../proof/autoscaling-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "${PROOF_DIR}"

echo "Writing proof to: ${PROOF_DIR}"

{
  echo "# Autoscaling proof — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "## ECS service desired counts (before)"
  aws ecs describe-services --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" \
    --services "${API_SERVICE_NAME}" "${WORKER_SERVICE_NAME}" \
    --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount}' \
    --output table
} | tee "${PROOF_DIR}/01-ecs-before.txt"

{
  echo "## Application Auto Scaling policies"
  aws application-autoscaling describe-scaling-policies \
    --region "${AWS_REGION}" \
    --service-namespace ecs \
    --output table
} | tee "${PROOF_DIR}/02-scaling-policies.txt"

{
  echo "## Scalable targets"
  aws application-autoscaling describe-scalable-targets \
    --region "${AWS_REGION}" \
    --service-namespace ecs \
    --output table
} | tee "${PROOF_DIR}/03-scalable-targets.txt"

{
  echo "## Live queue depth (API)"
  curl -sS "${API_BASE_URL}/metrics/queue" | python3 -m json.tool
} | tee "${PROOF_DIR}/04-queue-metrics.json"

{
  echo "## Rate limit config"
  curl -sS "${API_BASE_URL}/costs" | python3 -m json.tool
} | tee "${PROOF_DIR}/05-rate-limits.json"

echo ""
echo "Run load test: LOAD_TEST_URL=${API_BASE_URL} ./scripts/run_load_test.sh"
echo "Then re-run this script to capture after-state."
