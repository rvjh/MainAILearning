#!/usr/bin/env bash
# Verify required secrets exist and are not placeholders before deploying.
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"

PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"

check_secret() {
  local secret_id="$1"
  local value
  value="$(aws secretsmanager get-secret-value \
    --region "${AWS_REGION}" \
    --secret-id "${secret_id}" \
    --query SecretString \
    --output text)"

  if [[ -z "${value}" || "${value}" == "REPLACE_ME_BEFORE_DEPLOY" ]]; then
    echo "Secret not configured: ${secret_id}" >&2
    return 1
  fi
  echo "OK: ${secret_id}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CloudFormation may write redis://:/0 before ElastiCache is ready — sync from live cluster.
"${SCRIPT_DIR}/set_redis_secret.sh"

check_secret "${PROJECT_NAME}/redis-url"

REDIS_URL="$(aws secretsmanager get-secret-value \
  --region "${AWS_REGION}" \
  --secret-id "${PROJECT_NAME}/redis-url" \
  --query SecretString \
  --output text)"
if [[ "${REDIS_URL}" =~ ^redis://:[0-9]*/ || "${REDIS_URL}" == redis://:/0 ]]; then
  echo "Redis URL secret is malformed: ${REDIS_URL}" >&2
  exit 1
fi

check_secret "${PROJECT_NAME}/openai-api-key"

echo "All required secrets are configured."
