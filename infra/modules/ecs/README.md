# ecs module

This module defines the Product_A backend API compute on ECS Fargate for the dev MVP: an ECS cluster, a task definition, a private-subnet service (`ecs_desired_count = 0` for the initial phase), a CloudWatch Logs group, and optional autoscaling that is disabled by default.

- Requirements: Req 15.3, 16.2, 24.2, 25.1, 25.2
- Implemented in Task 9.2.

## Cluster and task definition

- Fargate cluster with Container Insights enabled and a `FARGATE` capacity provider.
- Task definition: `requires_compatibilities = ["FARGATE"]`, `network_mode = "awsvpc"`, `cpu = "256"`, `memory = "512"` (the MVP values; the variables validate the supported Fargate sizes).
- The single container uses `var.container_image` (an ECR URI), exposes `app_port` (default 8080), and ships logs to CloudWatch via the `awslogs` driver.
- `backend_execution_role_arn` and `backend_task_role_arn` are passed in from the iam module; this module creates no IAM role.

## Secrets Manager reference (ARN only, no plaintext)

`BACKEND_DB_SECRET_ARN` is placed in the normal environment as an ARN string only, and `BACKEND_DB_NAME` supplies the fallback database name. The Backend application uses its task role to fetch the DB secret at runtime. The secret payload is never placed in Terraform configuration or environment values.

`BACKEND_INTERNAL_BEARER_TOKEN` is injected through the ECS `secrets` block from `backend_bearer_secret_arn`. ECS uses the task execution role to resolve it at container startup.

## Service

- `ecs_desired_count = 0` initially and is changed to 1 after image publication and DB migration.
- `network_configuration` uses `private_subnet_ids` and `ecs_security_group_id` with a fixed `assign_public_ip = false`.
- `load_balancer` registers the container port with the alb module's `target_group_arn`.
- `ecs_desired_count` remains Terraform-owned so the two-phase 0→1 transition is applied.

## Autoscaling (designed in, MVP disabled)

`aws_appautoscaling_target` and `aws_appautoscaling_policy` are declared with `count = var.enable_autoscaling ? 1 : 0`. `enable_autoscaling` defaults to `false`, so the initial phase creates neither resource and keeps the service at `ecs_desired_count = 0`. After migration, the Operator changes it to 1 through a reviewed Terraform plan.

## One-off database migration task

The module also defines a separate `<name_prefix>-db-migration` Fargate task definition. It uses the dedicated migration execution/task roles and the `migration_container_image`; it is never attached to an ECS service. The runner receives only `BACKEND_DB_SECRET_ARN` and `BACKEND_DB_NAME`, writes to `/ecs/<name_prefix>-migration`, and is launched in the private application subnets by `scripts/deploy-migration.sh` after the initial infrastructure phase.

The Backend image and migration image remain separate. Migration SQL is packaged only by `apps/db-migration/Dockerfile`, whose build context is the repository root.

## Outputs

`cluster_arn`, `cluster_name`, `service_name`, `task_definition_arn`, `migration_cluster_arn`, `migration_task_definition_arn`. The log group names and all secret data are not root-facing outputs.

## dev root wiring

The dev root wires this module to network, ALB, ECR, Aurora and the IAM module. The first approved apply uses `ecs_desired_count=0`. After the five images are pushed and the one-off migration exits with code 0, the Operator changes the reviewed SSM input to 1 and runs a new plan/approval/apply.

## Not run by this module

This module does not run Terraform or contact AWS by itself. Local tests are static; real ECS deployment is Category C.
