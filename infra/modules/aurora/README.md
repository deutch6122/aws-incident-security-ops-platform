# aurora module

This module creates the Product_A Aurora PostgreSQL persistence boundary for the dev MVP. It is intentionally limited to infrastructure: **no schema, migration, initialization SQL, application IAM role, or application code is included**.

## MVP topology and network boundary

- Aurora PostgreSQL Serverless v2 cluster with exactly **one Writer instance and zero Reader instances**.
- Serverless v2 scaling defaults to **min 0.5 ACU / max 2 ACUs** and the instance class is `db.serverless`.
- The database subnet group consumes only `database_subnet_ids`, which must be the Task 4 network module's isolated DB subnet IDs in at least two AZs.
- The cluster attaches **only** `db_security_group_id`; the writer has `publicly_accessible = false`.
- The dev root wires `values(module.network.isolated_db_subnet_ids)` and `module.network.security_group_ids.db`, so Terraform establishes the network-to-Aurora dependency. The network module must be included and applied before Aurora exists; do not substitute public or private-app subnet IDs.

Aurora storage is managed redundantly across multiple Availability Zones by the service. The MVP reduces compute cost by using Writer 1 / Reader 0; it must **not** be described as a single-AZ database.

## Credentials and application contract

`manage_master_user_password = true` makes RDS generate and manage the master credential in AWS Secrets Manager. The module contains no `aws_secretsmanager_secret_version`, `master_password`, or password tfvars input. `master_username` is a validated non-sensitive value (`ops_admin` by default).

`master_user_secret_arn` and `app_database_secret_arn` expose only the generated secret ARN, never the value. A later ECS task role or EKS IRSA role must grant `secretsmanager:GetSecretValue` only for that ARN. This task does not create application IAM roles and does not modify the bootstrap `terraform-exec` role.

When `master_user_secret_kms_key_id` is null, the RDS-managed secret uses the AWS-managed Secrets Manager KMS key. A customer-managed KMS key, scoped application key policy, secret rotation schedule, and recovery/rotation runbook are production-phase extensions. Rotation must be designed and tested with application connection refresh behavior before enabling it.

## Inputs and dev defaults

| Input | Dev default | Notes |
| --- | --- | --- |
| `engine_version` | `16.6` | Module validation accepts Aurora PostgreSQL major 14–16. Before apply, verify the selected minor version supports Aurora Serverless v2 in the target Region. |
| `min_capacity` / `max_capacity` | `0.5` / `2` | Requirement 24.3 cost-oriented MVP capacity. |
| `backup_retention_period` | `1` day | Production needs a reviewed retention, recovery objective, and snapshot lifecycle. |
| `enabled_cloudwatch_logs_exports` | `postgresql` | Useful for dev diagnostics but incurs CloudWatch Logs ingestion/storage cost. |
| `performance_insights_enabled` | `false` | Enable only after production retention/access/cost review. |
| `deletion_protection` | `false` | Dev-only convenience; production should enable it. |
| `skip_final_snapshot` | `false` | Safer default: retain a final snapshot. Review snapshot naming, retention, cost, and recovery before destroy. |

`skip_final_snapshot = true` prioritizes quick dev teardown but can irreversibly remove data. The default `false` preserves a final snapshot, but can make repeated destroy/recreate workflows require a new `final_snapshot_identifier` and can retain billable snapshots. **Before any apply or destroy, explicitly review the chosen `skip_final_snapshot`, final-snapshot retention, and deletion-protection settings.**

## Cost and production expansion

Aurora Serverless v2 can still incur ongoing cost in dev, including the configured minimum ACU, storage, backup, and log costs. Before Phase 2 use, review the planned change and verify Aurora PostgreSQL Serverless v2 availability plus the chosen engine version in `ap-northeast-1`.

If that cost exceeds the MVP budget, the documented alternative is **RDS PostgreSQL single-AZ with a `db.t4g.micro`-class instance**. This module deliberately does not include an RDS conditional branch: selection must be an explicit, reviewed architecture decision.

For production, consider Reader instances, capacity limits based on load testing, longer automated backup retention and restore drills, Performance Insights, customer-managed KMS, secret rotation, deletion protection, and operational alarms. These are extensions; the Aurora storage redundancy across AZs remains distinct from the single Writer / zero Reader MVP compute topology.

## Outputs

All outputs are non-secret connection metadata: cluster/writer endpoints, port, database name, cluster identifiers, and the Secrets Manager **ARN**. No output includes a password or secret JSON value.

## Phase 2 pre-execution risks

1. Serverless v2 may generate continuous dev cost even at the 0.5 ACU floor.
2. Verify the selected engine version and Serverless v2 support in the actual deployment Region before apply.
3. Customer-managed KMS, secret rotation, backup retention, restore testing, and Performance Insights require production design decisions.
4. Explicitly confirm `skip_final_snapshot`, final snapshot retention, and deletion protection before an apply or destroy.

This module was designed for the approval-gated Infra_Pipeline workflow. It does not run Terraform or contact AWS by itself.
