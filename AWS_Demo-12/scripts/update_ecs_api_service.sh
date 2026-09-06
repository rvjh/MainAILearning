#!/usr/bin/env bash
# Force a new deployment of the ECS API service (picks up latest task definition / image).
set -euo pipefail

: "${CLUSTER_NAME:?Set CLUSTER_NAME}"
: "${API_SERVICE_NAME:?Set API_SERVICE_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_ENV="${PROJECT_ROOT}/aws/rendered/deploy.env"

if [[ -f "${DEPLOY_ENV}" ]]; then
  # shellcheck source=/dev/null
  source "${DEPLOY_ENV}"
fi

if [[ -n "${API_TASK_DEFINITION_ARN:-}" ]]; then
  aws ecs update-service \
    --cluster "${CLUSTER_NAME}" \
    --service "${API_SERVICE_NAME}" \
    --task-definition "${API_TASK_DEFINITION_ARN}" \
    --force-new-deployment
else
  aws ecs update-service \
    --cluster "${CLUSTER_NAME}" \
    --service "${API_SERVICE_NAME}" \
    --force-new-deployment
fi

echo "Triggered new deployment for API service: ${API_SERVICE_NAME}"
