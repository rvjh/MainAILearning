# ECR — Elastic Container Registry

ECR stores the Docker image built from this repo. API and worker services pull the **same image** with **different commands**.

## Teaching steps

1. Create an ECR repository (e.g. `aws-agent-deployment-demo`).
2. Build locally: `./scripts/build_image.sh`
3. Login: `./scripts/ecr_login.sh` (requires `AWS_ACCOUNT_ID`, `AWS_REGION`)
4. Push: `./scripts/push_to_ecr.sh` (requires `ECR_REPOSITORY`, optional `IMAGE_TAG`)

## Key points

- One image artifact, two runtime roles (API vs worker).
- Tag images with git SHA or semver — avoid relying on `:latest` in production.
- Enable image scanning for supply-chain hygiene.
- Lifecycle policies keep old images from accumulating cost.

## IAM

- CI/CD role needs `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`.
- ECS task **execution** role needs `ecr:BatchGetImage` and `ecr:GetDownloadUrlForLayer`.
