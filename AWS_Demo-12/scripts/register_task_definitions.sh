#!/usr/bin/env bash
# Register rendered ECS task definitions (creates new revisions).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RENDER_DIR="${PROJECT_ROOT}/aws/rendered"

: "${AWS_REGION:?Set AWS_REGION}"

if [[ ! -f "${RENDER_DIR}/task-definition-api.json" ]]; then
  echo "Missing rendered task definitions. Run ./scripts/render_task_definitions.sh first." >&2
  exit 1
fi

API_ARN="$(aws ecs register-task-definition \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${RENDER_DIR}/task-definition-api.json" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)"

WORKER_ARN="$(aws ecs register-task-definition \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${RENDER_DIR}/task-definition-worker.json" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)"

cat > "${RENDER_DIR}/deploy.env" <<EOF
API_TASK_DEFINITION_ARN=${API_ARN}
WORKER_TASK_DEFINITION_ARN=${WORKER_ARN}
EOF

echo "Registered API task definition:    ${API_ARN}"
echo "Registered worker task definition: ${WORKER_ARN}"
echo "Wrote ${RENDER_DIR}/deploy.env"
