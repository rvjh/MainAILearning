# Secrets Manager / SSM Parameter Store

Environment variables from `.env` locally become **runtime secrets** in AWS — never baked into the Docker image.

## What to store

| Variable | Secret? | Where | Which service |
|----------|---------|-------|---------------|
| `REDIS_URL` | Yes | Secrets Manager | API + worker |
| `OPENAI_API_KEY` | Yes | Secrets Manager | **Worker only** |
| `OPENAI_MODEL` | No | Task definition env | Worker |
| `APP_ENV`, `SERVICE_NAME` | No | Task definition env | Both |

## Production rule

> **The API never receives `OPENAI_API_KEY`.** LLM calls happen in the worker path only.

This follows least privilege: the public-facing API task role cannot invoke OpenAI even if compromised.

## Teaching steps

1. CloudFormation creates secrets (Redis URL auto-populated; OpenAI placeholder).
2. Set OpenAI key **after** stack deploy — never in CloudFormation parameters or git:

```bash
export OPENAI_API_KEY=sk-...
./scripts/set_openai_secret.sh
./scripts/verify_secrets.sh
```

3. ECS **execution role** pulls secrets at task startup via `secrets` block in task definition.
4. Rotate secrets with `put-secret-value` — redeploy tasks to pick up new values.

## Key points

- **Execution role** pulls secrets at task startup (ECS agent).
- **Task role** is for application runtime AWS API calls — keep them separate.
- Do not commit `.env` — use `.env.example` as documentation only.
- OpenAI key must not appear in CloudWatch logs — never log `OPENAI_API_KEY`.

## Teaching line

> Secrets should not be baked into the image.
