output "backend_execution_role_name" {
  description = "Name of the Backend ECS task execution role."
  value       = aws_iam_role.backend_execution.name
}

output "backend_execution_role_arn" {
  description = "ARN of the Backend ECS task execution role (passed to the ecs module)."
  value       = aws_iam_role.backend_execution.arn
}

output "backend_task_role_name" {
  description = "Name of the Backend ECS task role."
  value       = aws_iam_role.backend_task.name
}

output "backend_task_role_arn" {
  description = "ARN of the Backend ECS task role (passed to the ecs module)."
  value       = aws_iam_role.backend_task.arn
}

output "migration_execution_role_name" {
  description = "Name of the migration execution role."
  value       = aws_iam_role.migration_execution.name
}

output "migration_execution_role_arn" {
  description = "ARN of the migration execution role (passed to the ecs module)."
  value       = aws_iam_role.migration_execution.arn
}

output "migration_task_role_name" {
  description = "Name of the migration task role."
  value       = aws_iam_role.migration_task.name
}

output "migration_task_role_arn" {
  description = "ARN of the migration task role (passed to the ecs module)."
  value       = aws_iam_role.migration_task.arn
}

output "migration_launcher_role_name" {
  description = "Name of the migration-launcher role (body + trust only; RunTask policy attached by the dev root in Task 27)."
  value       = aws_iam_role.migration_launcher.name
}

output "migration_launcher_role_arn" {
  description = "ARN of the migration-launcher role."
  value       = aws_iam_role.migration_launcher.arn
}

output "passrole_target_role_arns" {
  description = "The exact four-ARN PassRole allowlist (Backend execution, Backend task, migration execution, migration task). The migration-launcher role is not a PassRole target."
  value = [
    aws_iam_role.backend_execution.arn,
    aws_iam_role.backend_task.arn,
    aws_iam_role.migration_execution.arn,
    aws_iam_role.migration_task.arn,
  ]
}
