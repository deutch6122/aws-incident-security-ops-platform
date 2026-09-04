# dev Terraform root

`infra/environments/dev` is the Terraform root for the dev-only AWS Incident & Security Operations Platform. It establishes versions, provider settings, validated common inputs, tags, naming, Task 4 network/ECR wiring, and Task 6.1 Aurora wiring.

## Files

- `versions.tf`: Terraform `>= 1.10` and AWS provider `~> 5.0`, matching `bootstrap/`.
- `providers.tf`: `ap-northeast-1` provider configuration and provider-level default tags.
- `variables.tf`: dev-only project/environment/Region inputs, optional tags, and validated naming suffixes.
- `locals.tf`: `ops-platform-dev` prefix, required common tags, and reusable generated resource names.
- `main.tf`: wires the Task 4 `network` and `ecr` modules, then Task 6.1 `aurora`. Aurora consumes only the network module's isolated DB subnet IDs and DB security group ID.
- `outputs.tf`: non-sensitive shared values only, including Aurora connection metadata and the Secrets Manager secret ARN (never a secret value).
- `terraform.tfvars.example`: non-sensitive example input. A real `terraform.tfvars` must not be committed.
- `backend.tf.example`: S3 remote backend example using `use_lockfile = true`.
- `tests/`: local naming unit/property/static tests; no Terraform or AWS access is needed.

## Naming and tags

All resource names use `ops-platform-dev-<resource>`. A suffix must consist of lowercase letters or digits separated by single hyphens; leading, trailing, and repeated hyphens are rejected, and the complete name is limited to 63 characters. Future modules should receive `local.name_prefix` and `local.common_tags`, or consume a validated entry from `local.resource_names`.

Required tags are `Project`, `Environment`, `Platform`, and `ManagedBy`. `additional_tags` may add non-sensitive metadata but cannot override those keys.

## Backend setup

Bootstrap creates the state bucket. For a controlled setup, copy `backend.tf.example` to the ignored `backend.tf`, replace `<account_id>` in `bucket` with the Bootstrap output, and keep `use_lockfile = true`. Terraform v1.10 or newer is required. S3 native locking is the preferred mechanism; a DynamoDB lock table remains only an optional compatibility alternative.

Do not commit `backend.tf`, `terraform.tfvars`, state, credentials, or secrets. Do not place secrets in tfvars.

## Aurora dependency and deployment policy

Task 6.1 connects `aurora` to the Task 4 `network` module through its isolated DB subnet IDs and database security group. This reference creates the Terraform dependency; do not deploy Aurora against public or private-app subnets. The Aurora module creates one Serverless v2 Writer and zero Readers, exposes only non-secret metadata plus the RDS-managed Secrets Manager ARN, and deliberately contains no schema or migration work.

Aurora Serverless v2 can incur ongoing dev cost. Before Phase 2 execution, verify the selected engine version and Serverless v2 support in `ap-northeast-1`, review KMS/rotation/backup choices, and explicitly confirm `skip_final_snapshot`, retained-snapshot cost, and deletion protection before apply or destroy. The module README documents the RDS PostgreSQL `db.t4g.micro` single-AZ alternative when Aurora cost exceeds the MVP budget.

Do not use repeated local `terraform apply` for the main infrastructure. The intended flow is pipeline `fmt` → `validate` → `plan` → manual approval → `apply`; no approval means no apply. This Task 6.1 implementation performed no Terraform command, AWS CLI command, authentication, or AWS resource operation.

## ALB / ECS (Task 9)

The `alb` and `ecs` modules were implemented in Task 9 (module bodies and static IaC snapshot tests). They are **not** wired into this dev root yet: they depend on inputs owned by later tasks — IAM execution/task roles (Task 10+), an ACM certificate, the ALB access-log S3 bucket, and the container image URI (built by App_Deploy). Wiring is deferred until those dependencies are confirmed, keeping the Task 4 "wire only what the task implements" policy intact.
