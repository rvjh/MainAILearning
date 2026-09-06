#!/usr/bin/env bash
# One-shot: infra + OpenAI secret + app deploy. Needs aws configure, Docker, OPENAI_API_KEY.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${AWS_REGION:?Export AWS_REGION first, e.g. export AWS_REGION=us-east-1}"
: "${OPENAI_API_KEY:?Export OPENAI_API_KEY before running this script}"

echo "=== AWS quick start (${AWS_REGION}) ==="

echo "=== 1/3 Infrastructure (~5–10 min for ElastiCache) ==="
"${SCRIPT_DIR}/deploy_infrastructure.sh"

echo "=== 2/3 OpenAI secret ==="
"${SCRIPT_DIR}/set_openai_secret.sh"
"${SCRIPT_DIR}/verify_secrets.sh"

echo "=== 3/3 Build, push, ECS services ==="
"${SCRIPT_DIR}/deploy_app.sh"

echo "Done. Teardown:"
echo "  aws cloudformation delete-stack --region ${AWS_REGION} --stack-name aws-agent-deployment-demo"
