#!/usr/bin/env bash
# Tag and push the image to ECR.
set -euo pipefail

: "${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID}"
: "${AWS_REGION:?Set AWS_REGION}"
: "${ECR_REPOSITORY:?Set ECR_REPOSITORY}"

IMAGE_TAG="${IMAGE_TAG:-latest}"
LOCAL_IMAGE="${LOCAL_IMAGE:-aws-agent-deployment-demo}"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}"

docker tag "${LOCAL_IMAGE}" "${ECR_URI}"
docker push "${ECR_URI}"

echo "Pushed: ${ECR_URI}"
