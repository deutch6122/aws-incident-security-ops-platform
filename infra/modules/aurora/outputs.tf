output "cluster_arn" {
  description = "ARN of the Aurora PostgreSQL cluster."
  value       = aws_rds_cluster.this.arn
}

output "cluster_id" {
  description = "Identifier of the Aurora PostgreSQL cluster."
  value       = aws_rds_cluster.this.id
}

output "cluster_endpoint" {
  description = "Non-sensitive writer endpoint for application connection configuration."
  value       = aws_rds_cluster.this.endpoint
}

output "writer_endpoint" {
  description = "Non-sensitive endpoint of the sole writer instance."
  value       = aws_rds_cluster_instance.writer.endpoint
}

output "port" {
  description = "PostgreSQL listener port."
  value       = aws_rds_cluster.this.port
}

output "database_name" {
  description = "Initial non-sensitive database name."
  value       = aws_rds_cluster.this.database_name
}

output "master_user_secret_arn" {
  description = "ARN of the RDS-managed Secrets Manager secret containing the master credential; the secret value is never output."
  value       = aws_rds_cluster.this.master_user_secret[0].secret_arn
}

output "app_database_secret_arn" {
  description = "Application-consumption alias for the RDS-managed master credential secret ARN. Future app IAM roles must limit secretsmanager:GetSecretValue to this ARN."
  value       = aws_rds_cluster.this.master_user_secret[0].secret_arn
}
