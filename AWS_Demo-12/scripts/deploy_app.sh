#!/usr/bin/env bash
# Full app deploy: build → ECR → register task defs → create/update ECS services → smoke test.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 1/8 Load stack outputs ==="
# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

echo ""
echo "=== 2/8 Verify Secrets Manager secrets ==="
"${SCRIPT_DIR}/verify_secrets.sh"

echo ""
echo "=== 3/8 Build image ==="
"${SCRIPT_DIR}/build_image.sh"

echo ""
echo "=== 4/8 Login and push to ECR ==="
"${SCRIPT_DIR}/ecr_login.sh"
"${SCRIPT_DIR}/push_to_ecr.sh"

echo ""
echo "=== 5/8 Render and register task definitions ==="
"${SCRIPT_DIR}/render_task_definitions.sh"
"${SCRIPT_DIR}/register_task_definitions.sh"

echo ""
echo "=== 6/8 Create ECS services (if first deploy) ==="
"${SCRIPT_DIR}/create_ecs_services.sh"

echo ""
echo "=== 7/8 Force new deployment ==="
"${SCRIPT_DIR}/update_ecs_api_service.sh"
"${SCRIPT_DIR}/update_ecs_worker_service.sh"

echo ""
echo "=== 8/8 Wait for API stability, then smoke test ==="
aws ecs wait services-stable \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --services "${API_SERVICE_NAME}"

echo "API service stable. Testing ALB endpoint: ${API_BASE_URL}"
"${SCRIPT_DIR}/test_api.sh"
"${SCRIPT_DIR}/test_job.sh"

echo ""
echo "Deploy complete."
echo "  ALB:        ${API_BASE_URL}"
echo "  CloudWatch: ${API_LOG_GROUP} and ${WORKER_LOG_GROUP}"
