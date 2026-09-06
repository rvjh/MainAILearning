#!/usr/bin/env bash
# Deploy autoscaling stack (API CPU + ALB traffic, worker Celery queue depth).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=load_stack_outputs.sh
source "${SCRIPT_DIR}/load_stack_outputs.sh"

STACK_AUTOSCALE="${STACK_NAME:-aws-agent-deployment-demo}-autoscaling"
PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"

AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
export AWS_ACCOUNT_ID

echo "=== Build and upload queue depth Lambda ==="
BUILD_OUT="$("${SCRIPT_DIR}/build_queue_depth_lambda.sh")"
echo "${BUILD_OUT}"
eval "$(echo "${BUILD_OUT}" | grep '^LAMBDA_ARTIFACT_BUCKET=')"
export LAMBDA_ARTIFACT_BUCKET

REDIS_URL="$(aws secretsmanager get-secret-value \
  --region "${AWS_REGION}" \
  --secret-id "${PROJECT_NAME}/redis-url" \
  --query SecretString --output text)"

TG_ARN="${API_TARGET_GROUP_ARN}"
LB_ARN="$(aws elbv2 describe-load-balancers --region "${AWS_REGION}" \
  --names "${PROJECT_NAME}-alb" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)"

# ALBRequestCountPerTarget label: app/<lb-name>/<lb-id>/targetgroup/<tg-name>/<tg-id>
LB_FULL="${LB_ARN#*:loadbalancer/}"
TG_FULL="targetgroup/${TG_ARN##*:targetgroup/}"
RESOURCE_LABEL="${LB_FULL}/${TG_FULL}"
echo "  AlbRequestCountResourceLabel=${RESOURCE_LABEL}"

VPC_ID="$(aws cloudformation describe-stacks --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Parameters[?ParameterKey=='VpcId'].ParameterValue | [0]" --output text)"
if [[ -z "${VPC_ID}" || "${VPC_ID}" == "None" ]]; then
  VPC_ID="$(aws ec2 describe-vpcs --region "${AWS_REGION}" \
    --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
fi

REDIS_SG="${REDIS_SECURITY_GROUP_ID:-}"
if [[ -z "${REDIS_SG}" || "${REDIS_SG}" == "None" ]]; then
  REDIS_SG="$(aws cloudformation describe-stack-resources --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "StackResources[?LogicalResourceId=='RedisSecurityGroup'].PhysicalResourceId | [0]" \
    --output text)"
fi
if [[ -z "${REDIS_SG}" || "${REDIS_SG}" == "None" ]]; then
  echo "Could not resolve Redis security group. Update main stack or set REDIS_SECURITY_GROUP_ID." >&2
  exit 1
fi
echo "  RedisSecurityGroupId=${REDIS_SG}"

echo "=== Deploy autoscaling stack: ${STACK_AUTOSCALE} ==="
aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_AUTOSCALE}" \
  --template-file "${PROJECT_ROOT}/aws/cloudformation/autoscaling.yaml" \
  --parameter-overrides \
    ProjectName="${PROJECT_NAME}" \
    ClusterName="${CLUSTER_NAME}" \
    ApiServiceName="${API_SERVICE_NAME}" \
    WorkerServiceName="${WORKER_SERVICE_NAME}" \
    VpcId="${VPC_ID}" \
    SubnetIds="${SUBNET_IDS}" \
    EcsSecurityGroupId="${ECS_SECURITY_GROUP_ID}" \
    RedisSecurityGroupId="${REDIS_SG}" \
    RedisUrl="${REDIS_URL}" \
    AlbRequestCountResourceLabel="${RESOURCE_LABEL}" \
    QueueDepthLambdaBucket="${LAMBDA_ARTIFACT_BUCKET}" \
    QueueDepthLambdaKey="queue_depth_publisher.zip" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo ""
echo "Autoscaling configured."
echo "  API:  CPU target + ALB requests per target"
echo "  Worker: custom metric ${PROJECT_NAME}/Celery QueueDepth"
echo "  Proof: ./scripts/prove_autoscaling.sh"
