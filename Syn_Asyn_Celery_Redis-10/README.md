# Sunday production working demo

This is the primary live demo for the Sunday session. Use it in two parts:

1. **Part 1 — intuition:** run the whole user journey before opening the implementation.
2. **Part 2 — production evidence:** explain the controls, then prove selected failure behavior.

The teaching line is:

> The queue delivers work. PostgreSQL defines truth. Repeated delivery is expected, so state and effects must be idempotent.

## Components

| Component | Responsibility |
|---|---|
| FastAPI | `202`, `Location`, GET status, DELETE cancellation, SSE, health probes |
| PostgreSQL | Durable jobs, idempotency, events, checkpoints, outbox, memory |
| Redis | Celery message delivery, not business truth |
| Celery worker | Late-ack execution and checkpointed workflow steps |
| Outbox publisher | Publishes only after the job transaction commits |
| LangGraph | Retrieve → plan → execute → persist workflow |
| Governed memory | Scoped recall and policy-controlled persistent writes |

## One-time schema upgrade after this pack update

The outbox now includes durable claims and delayed availability. PostgreSQL runs initialization files only for a new volume. If this folder was run before these columns were added, apply the idempotent schema upgrade once:

```bash
docker compose up -d postgres
docker compose exec -T postgres \
  psql -U agent -d agent_service \
  -f /docker-entrypoint-initdb.d/001-schema.sql
```

This keeps earlier demo jobs. The schema uses `ADD COLUMN IF NOT EXISTS` and rebuilds only the partial outbox index.

If earlier demo data is disposable, `docker compose down -v` followed by `docker compose up --build` also creates a clean volume. For a long-lived environment, use a versioned migration tool and a reviewed rollout rather than the classroom command.

## Start the stack

```bash
cd Sunday_Production_Working_Demo
cp .env.example .env
docker compose up --build
```

Wait for `postgres`, `redis`, `api`, `worker`, and `outbox` to become healthy. The API is at `http://localhost:8000`.

The default path is deterministic and does not require an external service. To use a real model through LangChain ChatOpenAI, set `OPENAI_API_KEY` and `OPENAI_MODEL` in `.env`.

## Prepare the client environment

In a second terminal:

```bash
cd Sunday_Production_Working_Demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Part 1 — show the complete system

Run this before opening the implementation:

```bash
python scripts/demo_full_flow.py
```

It shows:

- live and ready probes;
- `202 Accepted` and a stable job resource;
- create, replay, and idempotency conflict;
- cross-tenant not-found behavior;
- outbox → Celery → LangGraph execution;
- GET as authoritative state;
- SSE replay from `Last-Event-ID`;
- governed memory write, rejection, and later recall;
- durable cooperative cancellation.

Use `facilitator/CODE_REPO_EXPLANATION_SCRIPT.md` for the exact spoken explanation.

## Part 2 — prove production practices

The Compose file enables controlled demo faults with `ALLOW_DEMO_FAULTS=true`. After explaining the relevant code, run:

```bash
python scripts/demo_production_practices.py
```

It proves:

- the three idempotency branches;
- tenant-scoped resource identity;
- a typed transient failure waits, retries, and succeeds on attempt two;
- retry timing is stored through the outbox `available_at` field;
- a typed permanent failure stops after one attempt;
- the durable event order explains each state change.

Do not enable demo fault metadata in a public production service.

## Optional chaos checks

```bash
python scripts/demo_chaos.py
```

Use these after the core three-hour session or as take-home exploration.

## Stop

```bash
docker compose down
```

This retains the PostgreSQL volume. Add `-v` only when you intentionally want to delete this demo’s stored jobs.

## Storage design

| Table | Durable purpose |
|---|---|
| `agent_jobs` | Current state, attempts, checkpoint, cancellation, result, error, version |
| `idempotency_keys` | `(tenant_id, key)` → request hash and original job |
| `job_events` | Append-only event timeline and SSE cursor |
| `workflow_side_effects` | Unique `(job_id, step_key)` local result ledger |
| `job_outbox` | Delivery and retry intent with availability, claim, attempts, publication |
| `memories` | Scoped value, provenance, verification, expiry, supersession |
| `memory_audit` | Memory reads, writes, rejections, and deduplication decisions |

The create path inserts the job, idempotency record, initial events, and outbox row in one PostgreSQL transaction. The outbox publisher uses a durable claim token and `FOR UPDATE SKIP LOCKED`. If the claim owner dies, the claim can be recovered after a timeout.

Transient retries create another outbox row with a future `available_at` timestamp. Retry scheduling therefore survives a worker restart; no process must hold the delay only in memory.

## Guarantees implemented

- Tenant-scoped canonical idempotency with create, replay, and conflict branches
- Job, idempotency record, initial events, and delivery intent committed together
- Allowlisted state transitions with optimistic versions
- Atomic queued → running transition and attempt increment
- Durable outbox claims and delayed retry availability
- Late-ack Celery delivery with one application-owned business retry policy
- Typed transient, permanent, policy, and worker-loss failures
- Bounded exponential backoff and explicit dead-letter state
- Cooperative cancellation between workflow steps
- Durable per-step result ledger and checkpoints
- Durable SSE cursor replay with GET as truth
- Governed memory scope, provenance, rejection, expiry, and supersession

## Honest limits

- Demo headers stand in for validated OIDC or JWT claims.
- Controlled failure metadata is enabled only for teaching.
- The stack does not yet include worker leases and a reconciler for every possible stale-running job.
- A local step ledger does not replace provider idempotency, provider operation lookup, or compensation.
- TLS, quotas, migrations, secrets management, tracing, alerts, high availability, and backup/restore operations remain deployment work.
- Delivery is at least once. This project does not claim distributed exactly-once execution.

## Folder map

```text
Sunday_Production_Working_Demo/
  docker-compose.yml
  sql/schema.sql
  app/api.py
  app/service.py
  app/store.py
  app/celery_app.py
  app/worker.py
  app/agent_pipeline.py
  app/memory.py
  scripts/demo_full_flow.py
  scripts/demo_production_practices.py
  scripts/demo_chaos.py
  facilitator/CODE_REPO_EXPLANATION_SCRIPT.md
```
