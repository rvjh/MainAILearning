# AWS Agent Deployment Demo

Deploy FastAPI + Celery on ECS Fargate with Redis, Secrets Manager, ALB, and CloudWatch.

Same Docker image locally and on AWS. API and worker differ by **command**, **secrets**, **IAM**, and **scaling signal**.

```
Client → ALB → FastAPI (ECS) → Redis (ElastiCache) → Celery worker (ECS) → Tool Gateway → OpenAI
                                                      ↓
                                               CloudWatch Logs
```

| Local | AWS |
|-------|-----|
| Docker image | ECR |
| `api` service | ECS Fargate + ALB |
| `worker` service | ECS Fargate (no ALB) |
| `redis` | ElastiCache Redis |
| `.env` / `OPENAI_API_KEY` | Secrets Manager |
| `localhost:8000` | ALB DNS |

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for pytest)
- OpenAI API key
- **AWS CLI v2.32+** configured ([install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html))
  - Check: `aws --version` (must be ≥ 2.32 for `aws login`)
  - Sign in: `aws login` (or `aws login --remote` over SSH)
  - Verify: `aws sts get-caller-identity`
- Default VPC with at least 2 subnets in your region

```bash
cd aws-agent-deployment-demo
chmod +x scripts/*.sh
```

---

## Part 1 — Local run

### 1. Configure secrets

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY (never commit .env)
```

### 2. Start the stack

```bash
docker compose up --build
```

| Service | Role | Command |
|---------|------|---------|
| `redis` | Celery broker + result backend | `redis:7.4-alpine` |
| `api` | FastAPI on `:8000` | `uvicorn app.main:app ...` |
| `worker` | Celery consumer | `celery -A app.celery_app.celery_app worker ...` |

API and worker use the **same image**; only the command differs.

### 3. Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"aws-agent-deployment-demo","env":"local"}

API_BASE_URL=http://localhost:8000 ./scripts/test_api.sh
```

### 4. Submit and poll a job

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the deployment architecture?"}'

# Copy job_id, then:
curl http://localhost:8000/jobs/<job_id>

# Or end-to-end:
API_BASE_URL=http://localhost:8000 ./scripts/test_job.sh
```

### 5. Watch worker logs

```bash
docker compose logs -f worker
```

### 6. Unit tests (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

Interactive docs: http://localhost:8000/docs

---

## Part 2 — AWS deployment (step by step)

Work from the project root. Export your region once:

```bash
export AWS_REGION=us-east-1
```

### Option A — One-shot (recommended first time)

```bash
export OPENAI_API_KEY=sk-...
./scripts/quick_start_aws.sh
```

This runs: infrastructure → OpenAI secret → build/push/deploy → smoke tests.

### Option B — Explicit steps

#### Step 1 — Deploy infrastructure (once, ~5–10 min)

Creates ECR, ECS cluster, ElastiCache Redis, ALB, IAM roles, CloudWatch log groups, and Secrets Manager (`redis-url`). Does **not** create ECS services yet.

```bash
./scripts/deploy_infrastructure.sh
```

If you see `ResourceExistenceCheck` / named resources already exist:

```bash
FORCE_CLEAN=1 ./scripts/deploy_infrastructure.sh
```

Load stack outputs into your shell (needed by later scripts):

```bash
source ./scripts/load_stack_outputs.sh
echo "ALB: ${API_BASE_URL}"
echo "ECR: ${ECR_REPOSITORY}"
echo "Cluster: ${CLUSTER_NAME}"
```

#### Step 2 — Store the OpenAI secret

Never put the key in CloudFormation, git, or the image.

```bash
export OPENAI_API_KEY=sk-...
./scripts/set_openai_secret.sh
./scripts/verify_secrets.sh
```

#### Step 3 — Build the image (linux/amd64 for Fargate)

```bash
./scripts/build_image.sh
```

#### Step 4 — Push to ECR

```bash
./scripts/ecr_login.sh
./scripts/push_to_ecr.sh
```

#### Step 5 — Render and register ECS task definitions

```bash
./scripts/render_task_definitions.sh
./scripts/register_task_definitions.sh
```

Rendered files land in `aws/rendered/`. Worker task gets Redis + OpenAI secrets; API gets Redis only.

#### Step 6 — Create ECS services (first deploy only)

```bash
./scripts/create_ecs_services.sh
```

Safe to re-run — skips if services already exist.

#### Step 7 — Force a new deployment

```bash
./scripts/update_ecs_api_service.sh
./scripts/update_ecs_worker_service.sh
```

#### Step 8 — Smoke test against the ALB

```bash
aws ecs wait services-stable \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --services "${API_SERVICE_NAME}"

./scripts/test_api.sh
./scripts/test_job.sh
```

Or run steps 3–8 together anytime you change code:

```bash
./scripts/deploy_app.sh
```

### Pass criteria

| Check | Expect |
|-------|--------|
| `GET /health` | `"status": "ok"` |
| Job | `"status": "completed"` with OpenAI answer |
| CloudWatch | Logs under `/ecs/aws-agent-deployment-demo/api` and `.../worker` |
| Secrets | Referenced in task defs — not hardcoded |

Optional metrics:

```bash
curl -sS "${API_BASE_URL}/metrics/queue" | python3 -m json.tool
curl -sS "${API_BASE_URL}/costs" | python3 -m json.tool
```

### What each resource does

| Resource | Purpose |
|----------|---------|
| ECR | Same image as local |
| ECS cluster | Fargate runtime |
| ElastiCache Redis | Celery broker + results |
| ALB | Public API entry |
| ECS API service | FastAPI behind ALB — **no** OpenAI key |
| ECS worker service | Celery — Redis + OpenAI from Secrets Manager |
| Secrets Manager | `redis-url`, `openai-api-key` |
| CloudWatch | Separate api / worker log groups |
| IAM | Different task roles for API vs worker |

---

## Part 3 — Autoscaling (optional)

Run after a successful `deploy_app.sh`.

### 1. Configure scaling policies (once)

```bash
source ./scripts/load_stack_outputs.sh
./scripts/configure_autoscaling.sh
```

| Service | Scale signal |
|---------|--------------|
| API | ECS average CPU + ALB request count |
| Worker | Custom metric `QueueDepth` (`aws-agent-deployment-demo/Celery`) |

### 2. Baseline snapshot

```bash
./scripts/prove_autoscaling.sh
# Artifacts: proof/autoscaling-<timestamp>/
```

### 3. Live scale-out proof (worker first, then API)

```bash
./scripts/test_autoscaling_live_worker_first.sh
```

1. Reset desired count to 1  
2. Publish `QueueDepth=25` → worker desired ≥ 2  
3. Cooldown (~120s)  
4. ALB load → API desired ≥ 2  
5. Proof under `proof/autoscaling-live-worker-first-<timestamp>/`

Alternate (shorter gap between phases): `./scripts/test_autoscaling_live.sh`

Watch counts:

```bash
watch -n 10 "aws ecs describe-services --region \$AWS_REGION \
  --cluster aws-agent-deployment-demo-cluster \
  --services aws-agent-deployment-demo-api aws-agent-deployment-demo-worker \
  --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount}' \
  --output table"
```

### 4. Optional load / rate-limit test

```bash
source ./scripts/load_stack_outputs.sh
export LOAD_TEST_URL="${API_BASE_URL}"
CONCURRENCY=20 REQUESTS=60 ./scripts/run_load_test.sh
```

---

## Part 4 — Teardown

Delete autoscaling first (if you ran Part 3), then the main stack:

```bash
export AWS_REGION=us-east-1

aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo-autoscaling
aws cloudformation wait stack-delete-complete --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo-autoscaling

aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo
aws cloudformation wait stack-delete-complete --region "${AWS_REGION}" --stack-name aws-agent-deployment-demo

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
aws s3 rb "s3://aws-agent-deployment-demo-lambda-artifacts-${ACCOUNT_ID}" --force || true
```

Estimated cost while running: ~$0.07/hr + OpenAI usage (higher during load tests).

---

## Project structure

```
aws-agent-deployment-demo/
├── app/                      # FastAPI + Celery + governance
├── scripts/                  # Build, push, deploy, test, autoscaling
├── aws/cloudformation/       # Infra + autoscaling stacks
├── aws/task-definition-*.json
├── demo_outputs/             # Backup responses if live demo fails
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

Instructor timing notes: [`AWS_DEPLOYMENT.md`](AWS_DEPLOYMENT.md)  
CloudFormation params/outputs: [`aws/cloudformation/README.md`](aws/cloudformation/README.md)

---

## Governance (worker path)

```
run_agent_job → Tool Gateway → Policy → JIT → Tool handler → Audit JSONL
```

| Tool | Backend |
|------|---------|
| `deploy_catalog.get_architecture_context` | Mock catalog |
| `openai.generate_answer` | Real OpenAI |

OpenAI is never called directly from `tasks.py` — only via the gateway. Audit appends to `data/audit_events.jsonl`.

---

## Configuration

Local (`.env`):

```bash
REDIS_URL=redis://redis:6379/0
APP_ENV=local
SERVICE_NAME=aws-agent-deployment-demo
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

On AWS, `REDIS_URL` and `OPENAI_API_KEY` come from Secrets Manager (worker gets both; API gets Redis only).

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `POST` | `/jobs` | Enqueue job → `202` + `job_id` |
| `GET` | `/jobs/{job_id}` | Status / progress / result |
| `GET` | `/metrics/queue` | Celery queue depth |
| `GET` | `/costs` | Rate-limit / model surface |

## Scaling signals

| Service | Scales because | Signal |
|---------|----------------|--------|
| API | Users arrive | ALB RPS, CPU |
| Worker | Work accumulates | Queue depth |

## Production practices

| Practice | Implementation |
|----------|----------------|
| Secrets not in image | Secrets Manager / `.env` only |
| Least privilege | API has no OpenAI secret |
| Structured logs | JSON when `APP_ENV=production` |
| Retries | Celery autoretry with backoff |
| Separate scaling | API on RPS/CPU; worker on queue depth |
