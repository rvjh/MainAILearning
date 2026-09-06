# ElastiCache Redis

Redis is the Celery **broker** and **result backend** — the same role as the `redis` service in Docker Compose.

## Local → AWS mapping

| Local | AWS |
|-------|-----|
| `redis://redis:6379/0` | `redis://<elasticache-endpoint>:6379/0` |

## Teaching steps

1. Create ElastiCache Redis cluster (single node is fine for class; Multi-AZ for production).
2. Place in **private subnets** — never expose Redis to the internet.
3. Security group: allow inbound **6379** from ECS task security group only.
4. Store connection URL in Secrets Manager (see `secrets-manager-notes.md`).
5. Inject `REDIS_URL` into both API and worker task definitions.

## Key points

- Both API and worker must reach the same Redis endpoint.
- Use TLS in production (`rediss://`) when ElastiCache in-transit encryption is enabled.
- Auth token via Secrets Manager when Redis AUTH is enabled.
- Consider separate Redis databases or key prefixes if sharing a cluster across environments.

## Failure modes to discuss

- Redis unreachable → API accepts jobs but workers cannot process (teach observability).
- Redis full → result backend pressure; set TTLs and monitor memory.
