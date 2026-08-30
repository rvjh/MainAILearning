-- Production job service + governed memory (Sunday working demo)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN
  CREATE TYPE job_status AS ENUM (
    'accepted','queued','running','retrying','cancel_requested',
    'cancelled','succeeded','failed','dead_lettered'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS agent_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  user_id text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  payload jsonb NOT NULL,
  status job_status NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL,
  checkpoint_index integer NOT NULL DEFAULT 0,
  cancel_requested boolean NOT NULL DEFAULT false,
  next_retry_delay double precision,
  result jsonb,
  error text,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_jobs_tenant_status ON agent_jobs (tenant_id, status, updated_at);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  tenant_id text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  job_id uuid NOT NULL REFERENCES agent_jobs(job_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS job_events (
  cursor bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES agent_jobs(job_id),
  tenant_id text NOT NULL,
  event_type text NOT NULL,
  status job_status NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS job_events_replay ON job_events (tenant_id, job_id, cursor);

CREATE TABLE IF NOT EXISTS workflow_side_effects (
  job_id uuid NOT NULL REFERENCES agent_jobs(job_id),
  step_key text NOT NULL,
  output jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (job_id, step_key)
);

CREATE TABLE IF NOT EXISTS job_outbox (
  event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES agent_jobs(job_id),
  topic text NOT NULL,
  payload jsonb NOT NULL,
  available_at timestamptz NOT NULL DEFAULT now(),
  claimed_at timestamptz,
  claim_token uuid,
  publish_attempts integer NOT NULL DEFAULT 0,
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Idempotent upgrade path for demo volumes created by an earlier revision.
ALTER TABLE job_outbox ADD COLUMN IF NOT EXISTS available_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE job_outbox ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
ALTER TABLE job_outbox ADD COLUMN IF NOT EXISTS claim_token uuid;
ALTER TABLE job_outbox ADD COLUMN IF NOT EXISTS publish_attempts integer NOT NULL DEFAULT 0;

DROP INDEX IF EXISTS job_outbox_unpublished;
CREATE INDEX IF NOT EXISTS job_outbox_unpublished
  ON job_outbox (available_at, event_id)
  WHERE published_at IS NULL;

-- Governed memory (Saturday learnings, Postgres-backed)
CREATE TABLE IF NOT EXISTS memories (
  memory_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  user_id text NOT NULL,
  agent_id text NOT NULL,
  purpose text NOT NULL,
  kind text NOT NULL,
  subject text NOT NULL,
  memory_key text NOT NULL,
  value text NOT NULL,
  source_kind text NOT NULL,
  source_id text NOT NULL,
  evidence_excerpt text NOT NULL,
  verified boolean NOT NULL DEFAULT false,
  confidence double precision NOT NULL,
  sensitivity text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  expires_at timestamptz,
  supersedes_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memories_scope ON memories (tenant_id, user_id, agent_id, purpose, status);

CREATE TABLE IF NOT EXISTS memory_audit (
  audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  action text NOT NULL,
  tenant_id text NOT NULL,
  user_id text NOT NULL,
  detail text NOT NULL
);
