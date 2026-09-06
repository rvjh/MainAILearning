#!/usr/bin/env bash
# Smoke test — hit the /health endpoint.
set -euo pipefail

: "${API_BASE_URL:?Set API_BASE_URL (e.g. http://localhost:8000 or ALB DNS name)}"

curl -sS "${API_BASE_URL%/}/health" | python3 -m json.tool
