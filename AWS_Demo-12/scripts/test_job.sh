#!/usr/bin/env bash
# End-to-end job test — submit a job, poll until complete.
set -euo pipefail

: "${API_BASE_URL:?Set API_BASE_URL (e.g. http://localhost:8000 or ALB DNS name)}"

BASE="${API_BASE_URL%/}"

echo "Submitting job..."
SUBMIT_RESPONSE="$(curl -sS -X POST "${BASE}/jobs" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the deployment architecture?"}')"

echo "${SUBMIT_RESPONSE}" | python3 -m json.tool

JOB_ID="$(echo "${SUBMIT_RESPONSE}" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")"
echo "job_id: ${JOB_ID}"

echo "Polling job status..."
for _ in $(seq 1 20); do
  STATUS_RESPONSE="$(curl -sS "${BASE}/jobs/${JOB_ID}")"
  STATUS="$(echo "${STATUS_RESPONSE}" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")"

  if [[ "${STATUS}" == "completed" ]]; then
    echo "${STATUS_RESPONSE}" | python3 -m json.tool
    exit 0
  fi

  if [[ "${STATUS}" == "failed" ]]; then
    echo "${STATUS_RESPONSE}" | python3 -m json.tool
    exit 1
  fi

  sleep 1
done

echo "Timed out waiting for job ${JOB_ID}"
echo "${STATUS_RESPONSE}" | python3 -m json.tool
exit 1
