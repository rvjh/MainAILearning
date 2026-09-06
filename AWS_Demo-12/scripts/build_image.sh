#!/usr/bin/env bash
# Build linux/amd64 image for API and worker (required for ECS Fargate).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
docker build --platform "${PLATFORM}" -t aws-agent-deployment-demo .

echo "Built image: aws-agent-deployment-demo (${PLATFORM})"
