#!/usr/bin/env bash
# Deploy CloudFormation stack: ECR, ECS cluster, Redis, ALB, IAM, logs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

: "${AWS_REGION:?Set AWS_REGION}"

STACK_NAME="${STACK_NAME:-aws-agent-deployment-demo}"
PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"
FORCE_CLEAN="${FORCE_CLEAN:-0}"

resource_exists() {
  local kind="$1"
  case "${kind}" in
    ecr)
      aws ecr describe-repositories --region "${AWS_REGION}" \
        --repository-names "${PROJECT_NAME}" >/dev/null 2>&1
      ;;
    cluster)
      local status
      status="$(aws ecs describe-clusters --region "${AWS_REGION}" \
        --clusters "${PROJECT_NAME}-cluster" \
        --query 'clusters[0].status' --output text 2>/dev/null || true)"
      [[ "${status}" == "ACTIVE" ]]
      ;;
    log-api)
      aws logs describe-log-groups --region "${AWS_REGION}" \
        --log-group-name-prefix "/ecs/${PROJECT_NAME}/api" \
        --query "logGroups[?logGroupName=='/ecs/${PROJECT_NAME}/api'] | [0].logGroupName" \
        --output text 2>/dev/null | grep -q "/ecs/${PROJECT_NAME}/api"
      ;;
    log-worker)
      aws logs describe-log-groups --region "${AWS_REGION}" \
        --log-group-name-prefix "/ecs/${PROJECT_NAME}/worker" \
        --query "logGroups[?logGroupName=='/ecs/${PROJECT_NAME}/worker'] | [0].logGroupName" \
        --output text 2>/dev/null | grep -q "/ecs/${PROJECT_NAME}/worker"
      ;;
    *)
      return 1
      ;;
  esac
}

stack_status() {
  aws cloudformation describe-stacks --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NONE"
}

cleanup_orphans() {
  echo "Cleaning leftover named resources that block CloudFormation..."

  local status
  status="$(stack_status)"
  if [[ "${status}" == "REVIEW_IN_PROGRESS" || "${status}" == "ROLLBACK_COMPLETE" || "${status}" == "CREATE_FAILED" ]]; then
    echo "  Deleting stuck stack (${status})..."
    aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name "${STACK_NAME}"
    aws cloudformation wait stack-delete-complete --region "${AWS_REGION}" --stack-name "${STACK_NAME}"
  fi

  if resource_exists cluster; then
    local services
    services="$(aws ecs list-services --region "${AWS_REGION}" \
      --cluster "${PROJECT_NAME}-cluster" --query 'serviceArns[]' --output text 2>/dev/null || true)"
    if [[ -n "${services}" && "${services}" != "None" ]]; then
      for svc in ${services}; do
        echo "  Deleting ECS service ${svc}"
        aws ecs update-service --region "${AWS_REGION}" --cluster "${PROJECT_NAME}-cluster" \
          --service "${svc}" --desired-count 0 >/dev/null
        aws ecs delete-service --region "${AWS_REGION}" --cluster "${PROJECT_NAME}-cluster" \
          --service "${svc}" --force >/dev/null
      done
    fi
    echo "  Deleting ECS cluster ${PROJECT_NAME}-cluster"
    aws ecs delete-cluster --region "${AWS_REGION}" --cluster "${PROJECT_NAME}-cluster" >/dev/null
  fi

  if resource_exists ecr; then
    echo "  Deleting ECR repository ${PROJECT_NAME}"
    aws ecr delete-repository --region "${AWS_REGION}" \
      --repository-name "${PROJECT_NAME}" --force >/dev/null
  fi

  for lg in "/ecs/${PROJECT_NAME}/api" "/ecs/${PROJECT_NAME}/worker"; do
    if aws logs describe-log-groups --region "${AWS_REGION}" \
      --log-group-name-prefix "${lg}" \
      --query "logGroups[?logGroupName=='${lg}'] | [0].logGroupName" \
      --output text 2>/dev/null | grep -q "^${lg}$"; then
      echo "  Deleting log group ${lg}"
      aws logs delete-log-group --region "${AWS_REGION}" --log-group-name "${lg}"
    fi
  done
}

preflight_conflicts() {
  local conflicts=()
  resource_exists ecr && conflicts+=("ECR repository: ${PROJECT_NAME}")
  resource_exists cluster && conflicts+=("ECS cluster: ${PROJECT_NAME}-cluster")
  resource_exists log-api && conflicts+=("Log group: /ecs/${PROJECT_NAME}/api")
  resource_exists log-worker && conflicts+=("Log group: /ecs/${PROJECT_NAME}/worker")

  local status
  status="$(stack_status)"
  if [[ "${status}" == "REVIEW_IN_PROGRESS" || "${status}" == "ROLLBACK_COMPLETE" || "${status}" == "CREATE_FAILED" ]]; then
    conflicts+=("Stuck CloudFormation stack ${STACK_NAME} (${status})")
  fi

  if [[ ${#conflicts[@]} -eq 0 ]]; then
    return 0
  fi

  echo "Named resources already exist outside a healthy stack (CloudFormation ResourceExistenceCheck):"
  for item in "${conflicts[@]}"; do
    echo "  - ${item}"
  done
  echo ""
  echo "Fix with either:"
  echo "  FORCE_CLEAN=1 ./scripts/deploy_infrastructure.sh"
  echo "  # or a unique name:"
  echo "  PROJECT_NAME=aws-agent-deployment-demo-\$USER STACK_NAME=aws-agent-deployment-demo-\$USER ./scripts/deploy_infrastructure.sh"
  return 1
}

if [[ -z "${VPC_ID:-}" ]]; then
  VPC_ID="$(aws ec2 describe-vpcs --region "${AWS_REGION}" \
    --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' --output text)"
fi

if [[ -z "${SUBNET_IDS:-}" ]]; then
  SUBNET_IDS="$(aws ec2 describe-subnets --region "${AWS_REGION}" \
    --filters Name=vpc-id,Values="${VPC_ID}" \
    --query 'Subnets[0:2].SubnetId' --output text | tr '\t' ',')"
fi

if [[ "${FORCE_CLEAN}" == "1" ]]; then
  cleanup_orphans
elif ! preflight_conflicts; then
  exit 1
fi

echo "Deploying stack: ${STACK_NAME}"
echo "  Region:  ${AWS_REGION}"
echo "  VPC:     ${VPC_ID}"
echo "  Subnets: ${SUBNET_IDS}"
echo "ElastiCache usually takes 5–10 minutes."

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file "${PROJECT_ROOT}/aws/cloudformation/stack.yaml" \
  --parameter-overrides \
    ProjectName="${PROJECT_NAME}" \
    VpcId="${VPC_ID}" \
    SubnetIds="${SUBNET_IDS}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo "Syncing Redis URL into Secrets Manager..."
"${SCRIPT_DIR}/set_redis_secret.sh"

echo "Stack deployed. Next: source ./scripts/load_stack_outputs.sh"
