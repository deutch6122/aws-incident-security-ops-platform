output "cluster_arn" {
  description = "ARN of the ECS (Fargate) cluster."
  value       = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "Name of the backend API ECS service."
  value       = aws_ecs_service.this.name
}

output "task_definition_arn" {
  description = "ARN of the backend API task definition."
  value       = aws_ecs_task_definition.this.arn
}

output "migration_cluster_arn" {
  description = "ECS cluster ARN used to run the one-off migration task."
  value       = aws_ecs_cluster.this.arn
}

output "migration_task_definition_arn" {
  description = "ARN of the dedicated one-off DB migration task definition."
  value       = aws_ecs_task_definition.migration.arn
}
