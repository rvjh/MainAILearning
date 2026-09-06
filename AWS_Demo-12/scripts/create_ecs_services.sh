#!/usr/bin/env bash
# Create ECS services (run once after first image push and task definition registration).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

RENDER_DIR="${PROJECT_ROOT}/aws/rendered"
DEPLOY_ENV="${RENDER_DIR}/deploy.env"

if [[ ! -f "${DEPLOY_ENV}" ]]; then
  echo "Missing ${DEPLOY_ENV}. Run ./scripts/register_task_definitions.sh first." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${DEPLOY_ENV}"

IFS=',' read -r SUBNET_A SUBNET_B _ <<< "${SUBNET_IDS}"

service_exists() {
  local service_name="$1"
  local failures
  failures="$(aws ecs describe-services \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" \
    --services "${service_name}" \
    --query 'length(failures)' \
    --output text)"
  [[ "${failures}" == "0" ]]
}

if service_exists "${API_SERVICE_NAME}"; then
  echo "Service already exists: ${API_SERVICE_NAME}"
else
  aws ecs create-service \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" \
    --service-name "${API_SERVICE_NAME}" \
    --task-definition "${API_TASK_DEFINITION_ARN}" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_A},${SUBNET_B}],securityGroups=[${ECS_SECURITY_GROUP_ID}],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=${API_TARGET_GROUP_ARN},containerName=${API_CONTAINER_NAME},containerPort=8000" \
    --health-check-grace-period-seconds 60
  echo "Created API service: ${API_SERVICE_NAME}"
fi

if service_exists "${WORKER_SERVICE_NAME}"; then
  echo "Service already exists: ${WORKER_SERVICE_NAME}"
else
  aws ecs create-service \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" \
    --service-name "${WORKER_SERVICE_NAME}" \
    --task-definition "${WORKER_TASK_DEFINITION_ARN}" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_A},${SUBNET_B}],securityGroups=[${ECS_SECURITY_GROUP_ID}],assignPublicIp=ENABLED}"
  echo "Created worker service: ${WORKER_SERVICE_NAME}"
fi

echo "ECS services ready."
