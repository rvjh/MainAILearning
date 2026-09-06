#!/usr/bin/env bash
# Replace placeholders in task definition skeletons using stack outputs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

RENDER_DIR="${PROJECT_ROOT}/aws/rendered"
mkdir -p "${RENDER_DIR}"

render() {
  local src="$1"
  local dest="$2"
  sed \
    -e "s|AWS_ACCOUNT_ID|${AWS_ACCOUNT_ID}|g" \
    -e "s|AWS_REGION|${AWS_REGION}|g" \
    -e "s|ECR_REPOSITORY|${ECR_REPOSITORY}|g" \
    -e "s|IMAGE_TAG|${IMAGE_TAG}|g" \
    -e "s|EXECUTION_ROLE_ARN|${EXECUTION_ROLE_ARN}|g" \
    -e "s|TASK_ROLE_ARN|${3}|g" \
    -e "s|LOG_GROUP|${4}|g" \
    -e "s|CONTAINER_NAME|${5}|g" \
    -e "s|REDIS_URL_SECRET_ARN|${REDIS_URL_SECRET_ARN}|g" \
    -e "s|OPENAI_API_KEY_SECRET_ARN|${OPENAI_API_KEY_SECRET_ARN}|g" \
    "${src}" > "${dest}"
}

render \
  "${PROJECT_ROOT}/aws/task-definition-api.json" \
  "${RENDER_DIR}/task-definition-api.json" \
  "${API_TASK_ROLE_ARN}" \
  "${API_LOG_GROUP}" \
  "${API_CONTAINER_NAME}"

render \
  "${PROJECT_ROOT}/aws/task-definition-worker.json" \
  "${RENDER_DIR}/task-definition-worker.json" \
  "${WORKER_TASK_ROLE_ARN}" \
  "${WORKER_LOG_GROUP}" \
  "${WORKER_CONTAINER_NAME}"

echo "Rendered task definitions:"
echo "  ${RENDER_DIR}/task-definition-api.json"
echo "  ${RENDER_DIR}/task-definition-worker.json"
