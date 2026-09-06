#!/usr/bin/env bash
# Sync ElastiCache Redis endpoint into Secrets Manager (fixes empty redis://:/0 on first deploy).
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"

PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"
SECRET_ID="${SECRET_ID:-${PROJECT_NAME}/redis-url}"
CLUSTER_ID="${REDIS_CLUSTER_ID:-${PROJECT_NAME}-redis}"

ENDPOINT="$(aws elasticache describe-cache-clusters \
  --region "${AWS_REGION}" \
  --cache-cluster-id "${CLUSTER_ID}" \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.[Address,Port]' \
  --output text)"

read -r REDIS_HOST REDIS_PORT <<< "${ENDPOINT}"

if [[ -z "${REDIS_HOST}" || "${REDIS_HOST}" == "None" ]]; then
  echo "Could not resolve Redis endpoint for cluster: ${CLUSTER_ID}" >&2
  exit 1
fi

REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/0"

aws secretsmanager put-secret-value \
  --region "${AWS_REGION}" \
  --secret-id "${SECRET_ID}" \
  --secret-string "${REDIS_URL}"

echo "Redis URL stored in Secrets Manager: ${SECRET_ID}"
echo "  ${REDIS_URL}"
