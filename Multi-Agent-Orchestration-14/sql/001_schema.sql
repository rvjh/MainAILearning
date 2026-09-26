-- Migration 001. Docker executes this once on a fresh named volume.
BEGIN;
CREATE TABLE schema_migrations(version int PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE tenants(id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE principals(
 tenant_id uuid NOT NULL REFERENCES tenants, id uuid NOT NULL, subject text NOT NULL,
 role text NOT NULL CHECK(role IN ('requester','support_lead','finance_manager','finance_director','operator')),
 active boolean NOT NULL DEFAULT true, token_hash text NOT NULL UNIQUE,
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,subject));
CREATE TABLE orders(
 tenant_id uuid NOT NULL REFERENCES tenants, id uuid NOT NULL, customer_id uuid NOT NULL,
 delivered_at timestamptz NOT NULL, amount_minor bigint NOT NULL CHECK(amount_minor>0),
 currency char(3) NOT NULL CHECK(currency='INR'),
 category text NOT NULL CHECK(category IN ('standard','personalized','gift_card','consumed_digital')),
 PRIMARY KEY(tenant_id,id));
CREATE TABLE workflow_instances(
 tenant_id uuid NOT NULL REFERENCES tenants, id uuid NOT NULL, order_id uuid NOT NULL,
 requester_id uuid NOT NULL, idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
 request_hash text NOT NULL, state text NOT NULL CHECK(state IN
 ('RECEIVED','WAITING_APPROVAL','READY_TO_EXECUTE','EXECUTING','RETRY_WAIT','RECONCILING','COMPLETED','REJECTED','MANUAL_REVIEW','CLOSED')),
 version bigint NOT NULL DEFAULT 0, definition_version int NOT NULL DEFAULT 1,
 proposal_version int NOT NULL DEFAULT 1, amount_minor bigint NOT NULL CHECK(amount_minor>0),
 currency char(3) NOT NULL CHECK(currency='INR'), proposal jsonb NOT NULL,
 policy_version text NOT NULL, policy_snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,idempotency_key),
 FOREIGN KEY(tenant_id,order_id) REFERENCES orders(tenant_id,id),
 FOREIGN KEY(tenant_id,requester_id) REFERENCES principals(tenant_id,id),
 CHECK(jsonb_typeof(proposal)='object' AND jsonb_typeof(policy_snapshot)='object'));
-- Classroom: one refund workflow per order. Avoid multiple approved requests over-refunding one order.
CREATE UNIQUE INDEX one_refund_per_order ON workflow_instances(tenant_id,order_id);
CREATE INDEX workflow_state_age ON workflow_instances(tenant_id,state,updated_at);
CREATE TABLE approval_tasks(
 tenant_id uuid NOT NULL, id uuid NOT NULL, workflow_id uuid NOT NULL, stage int NOT NULL CHECK(stage>=1),
 required_role text NOT NULL CHECK(required_role IN ('support_lead','finance_manager','finance_director')),
 proposal_version int NOT NULL, status text NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','SUPERSEDED','EXPIRED')),
 version bigint NOT NULL DEFAULT 0, due_at timestamptz NOT NULL, supersedes_id uuid,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), closed_at timestamptz,
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,workflow_id,id), UNIQUE(tenant_id,workflow_id,stage),
 FOREIGN KEY(tenant_id,workflow_id) REFERENCES workflow_instances(tenant_id,id),
 FOREIGN KEY(tenant_id,workflow_id,supersedes_id) REFERENCES approval_tasks(tenant_id,workflow_id,id),
 CHECK((status='PENDING')=(closed_at IS NULL)));
CREATE UNIQUE INDEX one_pending_approval ON approval_tasks(tenant_id,workflow_id) WHERE status='PENDING';
CREATE INDEX pending_deadline ON approval_tasks(due_at) WHERE status='PENDING';
CREATE TABLE approval_decisions(
 tenant_id uuid NOT NULL, id uuid NOT NULL, task_id uuid NOT NULL, actor_id uuid NOT NULL,
 decision text NOT NULL CHECK(decision IN ('approve','reject')), reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 1000),
 proposal_version int NOT NULL, request_id uuid NOT NULL, command_key text NOT NULL, command_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(tenant_id,id),
 UNIQUE(tenant_id,task_id), UNIQUE(tenant_id,actor_id,command_key),
 FOREIGN KEY(tenant_id,task_id) REFERENCES approval_tasks(tenant_id,id),
 FOREIGN KEY(tenant_id,actor_id) REFERENCES principals(tenant_id,id));
CREATE TABLE workflow_timers(
 tenant_id uuid NOT NULL, id uuid NOT NULL, workflow_id uuid NOT NULL, task_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind='approval_deadline'), due_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('PENDING','FIRED','CANCELLED')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), fired_at timestamptz,
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,task_id,kind),
 FOREIGN KEY(tenant_id,workflow_id,task_id) REFERENCES approval_tasks(tenant_id,workflow_id,id));
CREATE INDEX due_timers ON workflow_timers(due_at) WHERE status='PENDING';
CREATE TABLE outbox_events(
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workflow_id uuid NOT NULL,
 aggregate_version bigint NOT NULL, event_type text NOT NULL, schema_version int NOT NULL DEFAULT 1,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 published_at timestamptz, attempts int NOT NULL DEFAULT 0 CHECK(attempts>=0),
 FOREIGN KEY(tenant_id,workflow_id) REFERENCES workflow_instances(tenant_id,id));
CREATE INDEX unpublished_events ON outbox_events(created_at) WHERE published_at IS NULL;
CREATE TABLE inbox_events(
 consumer text NOT NULL, event_id uuid NOT NULL, tenant_id uuid NOT NULL, workflow_id uuid NOT NULL,
 schema_version int NOT NULL, payload_hash text NOT NULL,
 received_at timestamptz NOT NULL DEFAULT clock_timestamp(), processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(consumer,event_id), FOREIGN KEY(tenant_id,workflow_id) REFERENCES workflow_instances(tenant_id,id));
CREATE TABLE execution_attempts(
 tenant_id uuid NOT NULL, id uuid NOT NULL, workflow_id uuid NOT NULL, operation_key text NOT NULL,
 attempt_no int NOT NULL CHECK(attempt_no>0), status text NOT NULL CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','RETRY','UNKNOWN','FAILED')),
 lease_owner text, lease_until timestamptz, fence bigint NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT clock_timestamp(), provider_receipt_id text, error_class text,
 started_at timestamptz, finished_at timestamptz,
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,operation_key,attempt_no),
 FOREIGN KEY(tenant_id,workflow_id) REFERENCES workflow_instances(tenant_id,id));
CREATE UNIQUE INDEX one_active_execution ON execution_attempts(tenant_id,workflow_id) WHERE status IN ('PENDING','RUNNING');
CREATE INDEX due_executions ON execution_attempts(status,available_at);
CREATE TABLE audit_events(
 tenant_id uuid NOT NULL, id uuid NOT NULL, workflow_id uuid NOT NULL, sequence_no bigint NOT NULL,
 event_type text NOT NULL, actor_id uuid, actor_kind text NOT NULL CHECK(actor_kind IN ('human','system')),
 actor_role_snapshot text, reason text, policy_version text NOT NULL, proposal_version int NOT NULL,
 request_id uuid, correlation_id uuid NOT NULL, causation_id uuid, details jsonb NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(tenant_id,id),
 UNIQUE(tenant_id,workflow_id,sequence_no), FOREIGN KEY(tenant_id,workflow_id) REFERENCES workflow_instances(tenant_id,id),
 FOREIGN KEY(tenant_id,actor_id) REFERENCES principals(tenant_id,id));
-- Denied requests may not have an authorized workflow reference.
CREATE TABLE security_events(id uuid PRIMARY KEY, actor_subject text, action text NOT NULL, outcome text NOT NULL,
 request_id uuid NOT NULL, occurred_at timestamptz NOT NULL DEFAULT clock_timestamp());
INSERT INTO schema_migrations(version) VALUES(1);
COMMIT;
