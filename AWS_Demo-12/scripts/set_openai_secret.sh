#!/usr/bin/env bash
# Store OpenAI API key in Secrets Manager (never in the Docker image or CloudFormation parameters).
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY — export your key, do not commit it}"

PROJECT_NAME="${PROJECT_NAME:-aws-agent-deployment-demo}"
SECRET_ID="${SECRET_ID:-${PROJECT_NAME}/openai-api-key}"

aws secretsmanager put-secret-value \
  --region "${AWS_REGION}" \
  --secret-id "${SECRET_ID}" \
  --secret-string "${OPENAI_API_KEY}"

echo "OpenAI API key stored in Secrets Manager: ${SECRET_ID}"
