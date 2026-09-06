# ECS Task Definition Skeletons

Teaching skeletons — **not valid JSON for direct `aws ecs register-task-definition` until placeholders are replaced.**

## Files

| File | Service | Command override |
|------|---------|------------------|
| `task-definition-api.json` | FastAPI API (behind ALB) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `task-definition-worker.json` | Celery worker (no ALB) | `celery -A app.celery_app.celery_app worker --loglevel=info` |

## Placeholders to replace

| Placeholder | Example |
|-------------|---------|
| `AWS_ACCOUNT_ID` | `123456789012` |
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `aws-agent-deployment-demo` |
| `IMAGE_TAG` | `latest` or git SHA |
| `EXECUTION_ROLE_ARN` | `arn:aws:iam::123456789012:role/ecsTaskExecutionRole` |
| `TASK_ROLE_ARN` | `arn:aws:iam::123456789012:role/agent-demo-api-task-role` (use **different** role for worker) |
| `LOG_GROUP` | `/ecs/aws-agent-deployment-demo/api` or `/worker` |
| `CONTAINER_NAME` | `agent-demo-api` or `agent-demo-worker` |
| `REDIS_URL` secret ARN | Full Secrets Manager ARN — API + worker |
| `OPENAI_API_KEY` secret ARN | Full Secrets Manager ARN — **worker only** |

## Teaching points

- **Same image** in both task definitions — only `command` differs.
- **Different task roles** — worker typically needs broader permissions.
- **`REDIS_URL`** comes from Secrets Manager — never baked into the image.
- **awslogs stream prefix** — use `api` vs `worker` for separate CloudWatch streams.

## Register (after replacing placeholders)

```bash
aws ecs register-task-definition --cli-input-json file://aws/task-definition-api.json
aws ecs register-task-definition --cli-input-json file://aws/task-definition-worker.json
```
