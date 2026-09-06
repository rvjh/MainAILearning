# ECS Worker Service — Fargate

The worker service runs Celery consumers. It does **not** need a load balancer.

## Architecture role

```
Redis queue → ECS Fargate (worker tasks) → CloudWatch logs
```

## Teaching steps

1. Register task definition from `task-definition-worker.json` (replace placeholders).
2. Create ECS service with:
   - Launch type: FARGATE
   - Desired count: 1–2 (start small for class)
   - **No load balancer**
   - Same cluster as API (or separate cluster in larger orgs)
3. Deploy updates: `./scripts/update_ecs_worker_service.sh`

## Scaling signal

**Scale on queue depth** — the worker scales because work accumulates.

- CloudWatch custom metric: Celery queue length (via Redis `LLEN` or exporter)
- Step scaling when queue depth exceeds threshold for N minutes
- Scale-in slowly to avoid thrashing during bursty agent workloads

## Key points

- Worker has **no public endpoint** — reduces attack surface.
- Worker task role can differ from API task role (e.g. S3 write, tool gateway invoke).
- Same Docker image as API; only the **command** changes:

```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```

- For production: consider separate worker pools for different task types (priority queues).

## Teaching line

> The API returns quickly. The worker proves the background system is alive.
