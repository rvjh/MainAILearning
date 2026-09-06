# IAM Roles for ECS Fargate

ECS tasks use two IAM roles. Confusing them is a common production mistake — call it out explicitly in class.

## Execution role (ECS agent)

Used by the ECS agent to **start** the container:

- Pull image from ECR
- Fetch secrets from Secrets Manager / SSM
- Write logs to CloudWatch

Example managed policy attachment: `AmazonECSTaskExecutionRolePolicy` (extend for Secrets Manager).

## Task role (application)

Used by **your code** at runtime:

- API task role: minimal — maybe read config, emit custom metrics
- Worker task role: broader — S3 artifacts, DynamoDB job store, invoke internal tool gateway, STS assume-role for JIT credentials

## Teaching line

> Same image. Different command. Different IAM. Different scaling signal.

## Recommended split for governed agentic systems

| Capability | API task role | Worker task role |
|------------|---------------|------------------|
| Read secrets | via execution role | via execution role |
| Write audit logs to S3 | optional | yes |
| Invoke Tool Gateway | no | yes |
| Assume JIT role (STS) | no | yes |
| Call external SaaS APIs | no | via gateway only |

## Key points

- Principle of least privilege per service.
- Worker typically needs more permissions — that's where agent actions happen.
- Never embed long-lived credentials; use IAM roles and short-lived tokens.
- Cross-account access: trust policies + external ID patterns.

## Placeholder ARNs in task definitions

Replace `EXECUTION_ROLE_ARN` and `TASK_ROLE_ARN` in:

- `aws/task-definition-api.json`
- `aws/task-definition-worker.json`

Use **different** task roles for API vs worker in production.
