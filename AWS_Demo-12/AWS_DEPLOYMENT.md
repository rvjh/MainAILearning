# Real AWS Deployment — Instructor Guide

Full learner steps (local → AWS → autoscaling → teardown) live in `[README.md](README.md)`.

This file is the **classroom timing** companion: prep before class, then Parts A–D during the session.

**The architecture does not change. The runtime changes.**

Live class demo on real AWS: ECR + ECS Fargate + ElastiCache + ALB + **Secrets Manager** + **OpenAI** (worker path only).

---

## What gets created


| Resource                  | Purpose                                                 |
| ------------------------- | ------------------------------------------------------- |
| **ECR**                   | Same Docker image as local                              |
| **ECS cluster**           | Fargate runtime                                         |
| **ElastiCache Redis**     | Celery broker + result backend                          |
| **ALB**                   | Public API endpoint                                     |
| **ECS API service**       | FastAPI behind ALB — **no OpenAI key**                  |
| **ECS worker service**    | Celery worker — **OpenAI + Redis from Secrets Manager** |
| **Secrets Manager**       | `redis-url`, `openai-api-key`                           |
| **CloudWatch log groups** | Separate `api` and `worker` streams (JSON in prod)      |
| **IAM roles**             | Different task roles for API vs worker                  |


---

## Before class (instructor prep)

### 1. Prerequisites

- AWS account + CLI configured - [https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- run the command - aws login
- Docker
- **OpenAI API key** (for Secrets Manager — not committed to git)

### 2. Deploy infrastructure

```bash
export AWS_REGION=us-east-1
chmod +x scripts/*.sh
./scripts/deploy_infrastructure.sh
```

If deploy fails with `ResourceExistenceCheck`, leftovers from a prior demo exist:

```bash
FORCE_CLEAN=1 ./scripts/deploy_infrastructure.sh
```

ElastiCache takes **5–10 minutes**.

### 3. Store OpenAI key in Secrets Manager

**Never** put the key in CloudFormation, git, or the Docker image:

```bash
export OPENAI_API_KEY=sk-...
./scripts/set_openai_secret.sh
./scripts/verify_secrets.sh
```

### 4. Local `.env` for Part A demo

```bash
cp .env.example .env
# Set OPENAI_API_KEY in .env for local worker
```

---

## During class

### Part A — Local (5 min)

```bash
docker compose up --build
API_BASE_URL=http://localhost:8000 ./scripts/test_job.sh
```

Teaching line: **The API returns quickly. The worker calls tools through the Gateway.**

Core governance line: **Agent proposes. Policy decides. Gateway executes. Audit proves.**

### Part B — Deploy to AWS (15 min)

```bash
export AWS_REGION=us-east-1
./scripts/deploy_app.sh
```

This verifies secrets, builds, pushes to ECR, registers task defs, updates ECS, and smoke-tests the ALB.

### Part C — Observability (5 min)

- CloudWatch → `/ecs/aws-agent-deployment-demo/worker` — gateway + OpenAI log lines
- Worker container → `data/audit_events.jsonl` (audit proof locally)
- Secrets Manager → confirm keys are referenced, not visible in task definition JSON
- ECS → API vs worker task roles differ; **Tool Gateway runs only in worker**

### Part D — Post-deploy validation + load / scaling tests (15–25 min)

Run these **after** `./scripts/deploy_app.sh` succeeds. Keep `AWS_REGION` set and load stack outputs when needed.

```bash
export AWS_REGION=us-east-1
source ./scripts/load_stack_outputs.sh
echo "ALB: ${API_BASE_URL}"
```

#### 1. Smoke validation (functional)

`deploy_app.sh` already runs these at the end. Re-run anytime to confirm the stack is healthy:

```bash
./scripts/test_api.sh    # GET /health → status ok
./scripts/test_job.sh    # POST /jobs → poll until completed (worker + OpenAI path)
```

**Pass criteria**


| Check                  | Expect                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| `/health`              | `"status": "ok"`                                                                           |
| Job status             | `"status": "completed"` with `governance.tools_invoked` including `openai.generate_answer` |
| CloudWatch worker logs | Gateway + OpenAI lines under `/ecs/aws-agent-deployment-demo/worker`                       |


Optional quick metrics check:

```bash
curl -sS "${API_BASE_URL}/metrics/queue" | python3 -m json.tool
curl -sS "${API_BASE_URL}/costs" | python3 -m json.tool
```

#### 2. Configure autoscaling (once per environment)

```bash
./scripts/configure_autoscaling.sh
```

This deploys stack `aws-agent-deployment-demo-autoscaling`:


| Service    | Scale signal                                                               |
| ---------- | -------------------------------------------------------------------------- |
| **API**    | ECS average CPU + ALB request count per target                             |
| **Worker** | Custom CloudWatch metric `aws-agent-deployment-demo/Celery` → `QueueDepth` |


Collect a before-load snapshot of policies and counts:

```bash
./scripts/prove_autoscaling.sh
```

Artifacts land under `proof/autoscaling-<timestamp>/`.

#### 3. Live autoscaling test (classroom proof)

Worker-first order keeps the scaling story clear (worker scale-out, cooldown, then API load):

```bash
./scripts/test_autoscaling_live_worker_first.sh
```

What it does:

1. Resets baseline desired count to **1** for API + worker
2. Publishes `QueueDepth=25` → expects **worker** desired count **≥ 2** (often scales to max)
3. Cooldown (~120s), then sustained ALB load → expects **API** desired count **≥ 2**
4. Writes proof under `proof/autoscaling-live-worker-first-<timestamp>/` including `SUMMARY.txt`

**Pass criteria:** both phases print `PASS` and summary shows worker + API scale-out succeeded.

Alternate (combined script, shorter gap between phases):

```bash
./scripts/test_autoscaling_live.sh
```

Watch live in another terminal:

```bash
watch -n 10 "aws ecs describe-services --region \$AWS_REGION \
  --cluster aws-agent-deployment-demo-cluster \
  --services aws-agent-deployment-demo-api aws-agent-deployment-demo-worker \
  --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount}' \
  --output table"
```

#### 4. Optional API load / rate-limit test

Lighter concurrency proof against `/health` and `/jobs` (not a full scale-out wait):

```bash
source ./scripts/load_stack_outputs.sh
export LOAD_TEST_URL="${API_BASE_URL}"
CONCURRENCY=20 REQUESTS=60 ./scripts/run_load_test.sh
```

Output: `proof/load-test-<timestamp>/load-test-summary.json`.

Teaching line: **API scales on request/CPU pressure; workers scale on queue depth — different signals for different roles.**

---

## Production practices to highlight

1. `**OPENAI_API_KEY` only on worker** — API cannot call OpenAI even if compromised
2. **Secrets Manager injection** — ECS execution role reads secrets at startup
3. **Same image, different command, different secrets, different IAM**
4. **Structured JSON logs** in production for CloudWatch Insights
5. **Celery autoretry** on transient OpenAI failures
6. **Tool Gateway in worker** — OpenAI only via `invoke_tool()`, not direct calls
7. **Audit JSONL** at `data/audit_events.jsonl` — compliance proof

---

## Teardown

Delete the autoscaling stack first (if you ran Part D), then the main stack:

```bash
export AWS_REGION=us-east-1
aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo-autoscaling
aws cloudformation wait stack-delete-complete --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo-autoscaling

aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo
aws cloudformation wait stack-delete-complete --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo
```

If autoscaling used a Lambda artifact bucket, remove it after stack delete:

```bash
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
aws s3 rb "s3://aws-agent-deployment-demo-lambda-artifacts-${ACCOUNT_ID}" --force || true
```

Estimated cost while running: ~$0.07/hr + OpenAI usage per job (higher during load / scale-out demos).