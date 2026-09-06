# Application Load Balancer (ALB)

The ALB is the public entry point for the FastAPI API service.

## Architecture role

```
Client → ALB (HTTPS) → Target Group → ECS API tasks :8000
```

The **worker service is not behind the ALB**.

## Teaching steps

1. Create ALB in public subnets.
2. Create target group: IP mode, port 8000, health check path `/health`.
3. Attach ECS API service to target group.
4. Listener: HTTPS (443) with ACM certificate; redirect HTTP → HTTPS.
5. Test: `./scripts/test_api.sh` with `API_BASE_URL=https://your-alb-dns-name`

## Key points

- Health checks hit `GET /health` — must return 200 quickly.
- Idle timeout and deregistration delay affect draining during deploys.
- WAF can sit in front of ALB for rate limiting and bot protection.
- ALB access logs → S3 for request audit trails.

## Scaling relationship

- ALB distributes traffic across API tasks.
- As RPS grows, scale **API** tasks — not workers.
- Workers scale independently based on queue depth.

## Teaching line

> The API scales because users arrive. The worker scales because work accumulates.
