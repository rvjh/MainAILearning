#!/usr/bin/env bash
# Scale API and worker back to minimum before autoscaling live tests.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"
METRIC_NAMESPACE="${PROJECT_NAME}/Celery"
MIN_CAPACITY="${MIN_CAPACITY:-1}"
MAX_CAPACITY="${MAX_CAPACITY:-4}"
WAIT_SECONDS="${RESET_WAIT_SECONDS:-120}"
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-role/ecs.application-autoscaling.amazonaws.com/AWSServiceRoleForApplicationAutoScaling_ECSService"

pin_service_to_min() {
  local service_name="$1"
  local resource_id="service/${CLUSTER_NAME}/${service_name}"
  aws application-autoscaling register-scalable-target \
    --region "${AWS_REGION}" \
    --service-namespace ecs \
    --resource-id "${resource_id}" \
    --scalable-dimension ecs:service:DesiredCount \
    --min-capacity "${MIN_CAPACITY}" \
    --max-capacity "${MIN_CAPACITY}" \
    --role-arn "${ROLE_ARN}" >/dev/null
  aws ecs update-service --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" --service "${service_name}" \
    --desired-count "${MIN_CAPACITY}" >/dev/null
}

restore_service_limits() {
  local service_name="$1"
  local resource_id="service/${CLUSTER_NAME}/${service_name}"
  aws application-autoscaling register-scalable-target \
    --region "${AWS_REGION}" \
    --service-namespace ecs \
    --resource-id "${resource_id}" \
    --scalable-dimension ecs:service:DesiredCount \
    --min-capacity "${MIN_CAPACITY}" \
    --max-capacity "${MAX_CAPACITY}" \
    --role-arn "${ROLE_ARN}" >/dev/null
}

echo "Pinning autoscaling to min=${MIN_CAPACITY} and scaling services in..."
pin_service_to_min "${API_SERVICE_NAME}"
pin_service_to_min "${WORKER_SERVICE_NAME}"

echo "Publishing QueueDepth=0 to ${METRIC_NAMESPACE}..."
aws cloudwatch put-metric-data --region "${AWS_REGION}" \
  --namespace "${METRIC_NAMESPACE}" \
  --metric-data "MetricName=QueueDepth,Value=0,Unit=Count"

echo "Waiting ${WAIT_SECONDS}s for scale-in..."
sleep "${WAIT_SECONDS}"

aws ecs wait services-stable --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --services "${API_SERVICE_NAME}" "${WORKER_SERVICE_NAME}"

echo "Restoring autoscaling max=${MAX_CAPACITY}..."
restore_service_limits "${API_SERVICE_NAME}"
restore_service_limits "${WORKER_SERVICE_NAME}"

aws ecs describe-services --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --services "${API_SERVICE_NAME}" "${WORKER_SERVICE_NAME}" \
  --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount}' \
  --output table

echo "Baseline reset complete."
