# CloudWatch Logs

Both API and worker tasks ship logs via the `awslogs` driver configured in task definitions.

## Log groups (recommended layout)

| Service | Log group | Stream prefix |
|---------|-----------|---------------|
| API | `/ecs/aws-agent-deployment-demo/api` | `api` |
| Worker | `/ecs/aws-agent-deployment-demo/worker` | `worker` |

Separate log groups (or stream prefixes) make live demos and incident response easier.

## Teaching steps

1. Create log groups before registering task definitions (or let ECS create them if IAM allows).
2. Execution role needs `logs:CreateLogStream`, `logs:PutLogEvents`.
3. During class: open CloudWatch → Log groups → filter worker streams for Celery task output.
4. Optionally ship logs to OpenSearch or a SIEM for audit retention.

## What students should see

- **API logs**: uvicorn access lines, request handling.
- **Worker logs**: Celery `run_agent_job` progress, workflow step names.

## Key points

- CloudWatch is the first line of **audit** and **debugging** for agent systems.
- Correlate API `job_id` with worker logs using the Celery task ID.
- Set retention policies — logs cost money at scale.
- For governed agentic architecture: structured JSON logs enable SIEM ingestion.

## Backup for live class

If AWS demo fails, use `demo_outputs/cloudwatch_log_sample.txt` and `demo_outputs/worker_log_sample.txt`.
