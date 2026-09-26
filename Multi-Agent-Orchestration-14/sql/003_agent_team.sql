-- Extension to the existing enterprise runtime. Money is integer paise.
BEGIN;
CREATE TABLE agent_cases(
 tenant_id uuid NOT NULL, id uuid NOT NULL, requester_id uuid NOT NULL, order_id uuid NOT NULL,
 amount_minor bigint NOT NULL CHECK(amount_minor>0), proposal_version int NOT NULL DEFAULT 1 CHECK(proposal_version=1),
 scenario text NOT NULL CHECK(scenario IN ('healthy','risk_timeout','conflict','missing_risk','malformed')),
 status text NOT NULL CHECK(status IN ('COLLECTING','READY','BLOCKED','SUBMITTED')),
 facts jsonb NOT NULL, snapshot jsonb, workflow_id uuid,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,order_id),
 FOREIGN KEY(tenant_id,requester_id) REFERENCES principals(tenant_id,id),
 FOREIGN KEY(tenant_id,order_id) REFERENCES orders(tenant_id,id),
 FOREIGN KEY(tenant_id,workflow_id) REFERENCES workflow_instances(tenant_id,id),
 CHECK((status IN ('READY','SUBMITTED'))=(snapshot IS NOT NULL)),
 CHECK((status='SUBMITTED')=(workflow_id IS NOT NULL)));
CREATE TABLE agent_tasks(
 tenant_id uuid NOT NULL, id uuid NOT NULL, case_id uuid NOT NULL,
 specialist text NOT NULL CHECK(specialist IN ('policy','order','risk')),
 round_no int NOT NULL CHECK(round_no BETWEEN 1 AND 2),
 status text NOT NULL CHECK(status IN ('RUNNING','SUCCEEDED','FAILED')),
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(), due_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,case_id,specialist,round_no),
 FOREIGN KEY(tenant_id,case_id) REFERENCES agent_cases(tenant_id,id));
CREATE TABLE agent_results(
 tenant_id uuid NOT NULL, task_id uuid NOT NULL, result jsonb NOT NULL,
 backend text NOT NULL, model_version text NOT NULL, prompt_version text NOT NULL,
 completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,task_id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES agent_tasks(tenant_id,id));
CREATE TABLE coordination_decisions(
 tenant_id uuid NOT NULL, id uuid NOT NULL, case_id uuid NOT NULL,
 round_no int NOT NULL CHECK(round_no BETWEEN 1 AND 2),
 action text NOT NULL CHECK(action IN ('FOLLOW_UP','READY','BLOCKED')),
 target text CHECK(target IN ('policy','order','risk')), reason text NOT NULL,
 input_snapshot jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,case_id,round_no),
 FOREIGN KEY(tenant_id,case_id) REFERENCES agent_cases(tenant_id,id));
CREATE INDEX agent_tasks_by_case ON agent_tasks(tenant_id,case_id,round_no);
CREATE FUNCTION protect_team_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.facts IS DISTINCT FROM OLD.facts OR NEW.amount_minor<>OLD.amount_minor
    OR NEW.proposal_version<>OLD.proposal_version OR NEW.order_id<>OLD.order_id THEN
  RAISE EXCEPTION 'Create a new governed proposal for changed evidence or amount';
 END IF;
 IF OLD.status IN ('READY','SUBMITTED') AND NEW.snapshot IS DISTINCT FROM OLD.snapshot THEN
  RAISE EXCEPTION 'Frozen evidence cannot change after readiness';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER team_snapshot_guard BEFORE UPDATE ON agent_cases
 FOR EACH ROW EXECUTE FUNCTION protect_team_snapshot();
GRANT SELECT,INSERT,UPDATE ON agent_cases,agent_tasks TO lab_app;
GRANT SELECT,INSERT ON agent_results,coordination_decisions TO lab_app;
INSERT INTO schema_migrations(version) VALUES(3);
COMMIT;
