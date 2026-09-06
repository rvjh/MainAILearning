# CloudFormation Stack

Deploys real AWS infrastructure for the live class demo.

## Deploy

```bash
export AWS_REGION=us-east-1
./scripts/deploy_infrastructure.sh
```

## Delete (after class)

```bash
aws cloudformation delete-stack \
  --region "${AWS_REGION}" \
  --stack-name aws-agent-deployment-demo
```

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `ProjectName` | `aws-agent-deployment-demo` | Prefix for resource names |
| `VpcId` | (required) | Auto-detected default VPC by deploy script |
| `SubnetIds` | (required) | First two subnets in VPC, auto-detected |

## Outputs

Used by `scripts/load_stack_outputs.sh`:

- ECS cluster name
- ECR repository name
- ALB DNS name
- IAM role ARNs
- Redis secret ARN
- Security group and subnet IDs
- CloudWatch log group names

ECS **services** are created by `scripts/create_ecs_services.sh` after the first image push — not in this stack — so learners see the full deploy cycle.
