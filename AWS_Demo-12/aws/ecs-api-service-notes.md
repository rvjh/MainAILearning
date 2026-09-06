# ECS API Service — Fargate

The API service runs the FastAPI container behind an Application Load Balancer (ALB).

## Architecture role

```
Internet → ALB → ECS Fargate (API tasks) → Redis (ElastiCache)
```

## Teaching steps

1. Register task definition from `task-definition-api.json` (replace placeholders).
2. Create ECS cluster (Fargate).
3. Create service with:
   - Launch type: FARGATE
   - Desired count: 2 (teaching default for HA)
   - Load balancer: attach to ALB target group on port 8000
   - Health check path: `/health`
4. Deploy updates: `./scripts/update_ecs_api_service.sh`

## Scaling signal

**Scale on RPS and latency** — the API scales because users arrive.

- Target tracking on `ALBRequestCountPerTarget`
- Or target tracking on `ECSServiceAverageCPUUtilization` as a secondary signal
- Response time alarms for p95 latency

## Key points

- API sits behind ALB — this is the public entry point.
- Health check must match `GET /health`.
- Place tasks in **private subnets**; ALB sits in public subnets.
- Security group: allow inbound from ALB security group on port 8000 only.
- Use a **task role** scoped to what the API needs (read secrets, minimal AWS API access).

## Same image, different command

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
