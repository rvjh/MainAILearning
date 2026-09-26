-- Run with lab_admin for classroom investigation, never to repair state.
SELECT id,status,scenario,amount_minor,proposal_version,workflow_id FROM agent_cases ORDER BY created_at DESC LIMIT 8;
SELECT t.case_id,t.specialist,t.round_no,t.status,r.result,r.backend
FROM agent_tasks t LEFT JOIN agent_results r ON r.tenant_id=t.tenant_id AND r.task_id=t.id
ORDER BY t.started_at DESC LIMIT 20;
SELECT case_id,round_no,action,target,reason FROM coordination_decisions ORDER BY created_at DESC LIMIT 10;
SELECT id,state,proposal->>'team_case_id' AS team_case,proposal->>'team_snapshot_hash' AS frozen_evidence
FROM workflow_instances ORDER BY created_at DESC LIMIT 8;
