# ecs module

This module defines the Product_A backend API compute on ECS Fargate for the dev MVP: an ECS cluster, a task definition (CPU 256 / Memory 512, database credential read via Secrets Manager), a service (`desired_count = 1`, private subnets), a CloudWatch Logs group, and a design-only autoscaling target/policy that is disabled by default.

- Requirements: Req 15.3, 16.2, 24.2, 25.1, 25.2
- Implemented in Task 9.2.

## Cluster and task definition

- Fargate cluster with Container Insights enabled and a `FARGATE` capacity provider.
- Task definition: `requires_compatibilities = ["FARGATE"]`, `network_mode = "awsvpc"`, `cpu = "256"`, `memory = "512"` (the MVP values; the variables validate the supported Fargate sizes).
- The single container uses `var.container_image` (an ECR URI), exposes `app_port` (default 8080), and ships logs to CloudWatch via the `awslogs` driver.
- `execution_role_arn` and `task_role_arn` are passed in from the iam module; this module creates no IAM role.

## Secrets Manager reference (ARN only, no plaintext)

The database credential is injected through the ECS `secrets` block: `valueFrom = var.db_secret_arn` (for example the aurora module's `app_database_secret_arn`). This is an **ARN reference only**. The module never contains a password, a full connection string, a token, or any secret value, and no such value is placed in `environment`. The task execution role must scope `secretsmanager:GetSecretValue` to that ARN.

## Service

- `desired_count = 1` (MVP), `launch_type = FARGATE`.
- `network_configuration` uses `private_subnet_ids` and `ecs_security_group_id` with `assign_public_ip = false`, so tasks run only in private application subnets.
- `load_balancer` registers the container port with the alb module's `target_group_arn`.
- `desired_count` is in `ignore_changes` so that, if autoscaling is later enabled, the scaling policy owns the running count.

## Autoscaling (designed in, MVP disabled)

`aws_appautoscaling_target` and `aws_appautoscaling_policy` are declared with `count = var.enable_autoscaling ? 1 : 0`. `enable_autoscaling` defaults to `false`, so the MVP creates neither resource and the task count stays at `desired_count = 1`. Enabling it later provides target-tracking CPU autoscaling without a structural change.

## Outputs

`cluster_arn`, `cluster_name`, `service_name`, `task_definition_arn`, `log_group_name`. No secret value is output.

## dev root wiring

This module is **not** wired into the dev root in Task 9. It depends on inputs owned by later tasks — the IAM execution/task roles (Task 10+), the container image URI (built and pushed by App_Deploy), and the alb target group. Wiring is deferred until those exist, preserving the Task 4 "wire only what the task implements" policy.

## Not run by this module

This module does not run Terraform (`init`/`validate`/`plan`/`apply`) and does not contact AWS. The Task 9.3 tests are static text/regex checks only.
