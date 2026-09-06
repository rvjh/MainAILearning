#!/usr/bin/env bash
# Package queue-depth Lambda and upload to S3 for the autoscaling stack.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"

: "${AWS_REGION:?Set AWS_REGION}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
BUCKET="${LAMBDA_ARTIFACT_BUCKET:-${PROJECT_NAME}-lambda-artifacts-${AWS_ACCOUNT_ID}}"
KEY="${QUEUE_DEPTH_LAMBDA_KEY:-queue_depth_publisher.zip}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

cp "${PROJECT_ROOT}/lambda/queue_depth_publisher/lambda_function.py" "${BUILD_DIR}/"

pip install --quiet --no-cache-dir redis \
  -t "${BUILD_DIR}" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: 2>/dev/null \
  || pip install --quiet --no-cache-dir redis -t "${BUILD_DIR}"

(
  cd "${BUILD_DIR}"
  zip -qr "${BUILD_DIR}/package.zip" .
)

if ! aws s3api head-bucket --bucket "${BUCKET}" --region "${AWS_REGION}" 2>/dev/null; then
  aws s3 mb "s3://${BUCKET}" --region "${AWS_REGION}"
fi

aws s3 cp "${BUILD_DIR}/package.zip" "s3://${BUCKET}/${KEY}" --region "${AWS_REGION}"

echo "LAMBDA_ARTIFACT_BUCKET=${BUCKET}"
echo "Uploaded s3://${BUCKET}/${KEY}"
