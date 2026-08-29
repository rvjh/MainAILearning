CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memories (
    memory_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    value JSONB NOT NULL,
    provenance JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    sensitivity TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    supersedes_id UUID REFERENCES memories(memory_id),
    status TEXT NOT NULL CHECK (status IN ('active','superseded','deleted')),
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memories_scope_idx
ON memories(tenant_id, user_id, agent_id, purpose, kind, status);

CREATE INDEX IF NOT EXISTS memories_embedding_hnsw_idx
ON memories USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS memory_audit (
    event_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    action TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    memory_id UUID,
    policy_version TEXT NOT NULL,
    detail JSONB NOT NULL
);

-- Production queries must include scope/status/expiry predicates before LIMIT.

