#!/usr/bin/env bash
# Export CloudFormation outputs as shell variables for deploy scripts.
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"

STACK_NAME="${STACK_NAME:-aws-agent-deployment-demo}"

query_output() {
  aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='${1}'].OutputValue | [0]" \
    --output text
}

export AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
export AWS_REGION
export STACK_NAME
export CLUSTER_NAME="$(query_output ClusterName)"
export ECR_REPOSITORY="$(query_output EcrRepositoryName)"
export ALB_DNS_NAME="$(query_output AlbDnsName)"
export API_TARGET_GROUP_ARN="$(query_output ApiTargetGroupArn)"
export EXECUTION_ROLE_ARN="$(query_output ExecutionRoleArn)"
export API_TASK_ROLE_ARN="$(query_output ApiTaskRoleArn)"
export WORKER_TASK_ROLE_ARN="$(query_output WorkerTaskRoleArn)"
export REDIS_URL_SECRET_ARN="$(query_output RedisUrlSecretArn)"
export OPENAI_API_KEY_SECRET_ARN="$(query_output OpenAiApiKeySecretArn)"
export ECS_SECURITY_GROUP_ID="$(query_output EcsSecurityGroupId)"
export API_LOG_GROUP="$(query_output ApiLogGroupName)"
export WORKER_LOG_GROUP="$(query_output WorkerLogGroupName)"
export SUBNET_IDS="$(query_output SubnetIds)"
export API_SERVICE_NAME="${API_SERVICE_NAME:-aws-agent-deployment-demo-api}"
export WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-aws-agent-deployment-demo-worker}"
export API_CONTAINER_NAME="${API_CONTAINER_NAME:-agent-demo-api}"
export WORKER_CONTAINER_NAME="${WORKER_CONTAINER_NAME:-agent-demo-worker}"
export IMAGE_TAG="${IMAGE_TAG:-latest}"
export API_BASE_URL="${API_BASE_URL:-http://${ALB_DNS_NAME}}"

echo "Loaded stack outputs from: ${STACK_NAME}"
echo "  CLUSTER_NAME=${CLUSTER_NAME}"
echo "  ECR_REPOSITORY=${ECR_REPOSITORY}"
echo "  ALB_DNS_NAME=${ALB_DNS_NAME}"
echo "  API_BASE_URL=${API_BASE_URL}"
